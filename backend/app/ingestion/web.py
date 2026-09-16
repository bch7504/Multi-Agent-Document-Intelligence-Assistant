"""Load, chunk, and serialize documents from web sources."""

import json
import os
import re
from hashlib import sha256
from urllib.parse import urlparse
from uuid import NAMESPACE_URL, UUID, uuid5

os.environ.setdefault("USER_AGENT", "RAG-LangChain/1.0")

from langchain_community.document_loaders import RecursiveUrlLoader, WebBaseLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from bs4 import BeautifulSoup


DEFAULT_HEADERS = {"User-Agent": os.environ["USER_AGENT"]}
DEFAULT_DOCUMENTATION_URL = "https://docs.stackai.com/llms-full.txt"
CRAWL_EXCLUDED_PATHS = ("~gitbook/image", "spaces/", "files/")
DEFAULT_CHUNK_SIZE_TOKENS = 500
DEFAULT_CHUNK_OVERLAP_TOKENS = 75
CHUNK_SEPARATORS = ("\n\n", "\n", ". ", "! ", "? ", "; ", " ", "")


def _positive_int_env(name: str, default: int, *, minimum: int = 1) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        value = int(raw_value)
    except ValueError as error:
        raise ValueError(f"{name} must be an integer") from error
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}")
    return value


def build_text_splitter() -> RecursiveCharacterTextSplitter:
    """Build a token-aware splitter while preserving paragraph boundaries."""
    chunk_size = _positive_int_env(
        "CHUNK_SIZE_TOKENS",
        DEFAULT_CHUNK_SIZE_TOKENS,
    )
    chunk_overlap = _positive_int_env(
        "CHUNK_OVERLAP_TOKENS",
        DEFAULT_CHUNK_OVERLAP_TOKENS,
        minimum=0,
    )
    if chunk_overlap >= chunk_size:
        raise ValueError("CHUNK_OVERLAP_TOKENS must be smaller than CHUNK_SIZE_TOKENS")

    return RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        encoding_name=os.getenv("CHUNK_TOKEN_ENCODING", "cl100k_base"),
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=list(CHUNK_SEPARATORS),
        add_start_index=True,
    )


def _stable_uuid(value: object, fallback: str) -> UUID:
    if value:
        try:
            return UUID(str(value))
        except ValueError:
            return uuid5(NAMESPACE_URL, str(value))
    return uuid5(NAMESPACE_URL, fallback)


def add_chunk_provenance(documents, source_name: str | None = None):
    """Attach stable document/chunk identifiers required for scoped retrieval."""
    document_indexes: dict[str, int] = {}
    for document in documents:
        metadata = document.metadata
        source = str(metadata.get("source") or source_name or "unknown-source")
        document_id = _stable_uuid(
            metadata.get("document_id"),
            f"document::{source_name or source}",
        )
        document_key = str(document_id)
        chunk_index = document_indexes.get(document_key, 0)
        document_indexes[document_key] = chunk_index + 1
        try:
            start_index = max(0, int(metadata.get("start_index") or 0))
        except (TypeError, ValueError):
            start_index = 0
        content_digest = sha256(document.page_content.encode("utf-8")).hexdigest()
        chunk_id = _stable_uuid(
            metadata.get("chunk_id"),
            f"chunk::{document_id}::{chunk_index}::{start_index}::{content_digest}",
        )
        metadata.update(
            {
                "document_id": str(document_id),
                "chunk_id": str(chunk_id),
                "chunk_index": chunk_index,
                "start_index": start_index,
                "source_name": str(
                    metadata.get("source_name")
                    or source_name
                    or metadata.get("title")
                    or source
                )[:255],
            }
        )
    return documents


def _validate_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("URL must be an absolute http:// or https:// URL")
    return url


def _crawl_exclude_dirs(url: str) -> tuple[str, ...]:
    parsed = urlparse(_validate_url(url))
    base_url = f"{parsed.scheme}://{parsed.netloc}/"
    return tuple(f"{base_url}{path}" for path in CRAWL_EXCLUDED_PATHS)


def metadata_extractor(raw_content: str, url: str, response) -> dict:
    content_type = response.headers.get("Content-Type", "")
    metadata = {"source": url, "content_type": content_type}
    if "html" not in content_type.lower():
        return metadata

    soup = BeautifulSoup(raw_content, "html.parser")
    if title := soup.find("title"):
        metadata["title"] = title.get_text(strip=True)[:1_000]
    if description := soup.find("meta", attrs={"name": "description"}):
        metadata["description"] = str(description.get("content") or "")[:4_000]
    if html := soup.find("html"):
        metadata["language"] = str(html.get("lang") or "")[:32]
    return metadata

def bs4_extractor(html: str) -> str:
    """
    Hàm trích xuất nội dung văn bản từ HTML sử dụng BeautifulSoup
    Args:
        html: Chuỗi HTML cần xử lý
    Returns:
        str: Văn bản đã dược làm sạch, loại bỏ các thẻ HTML và khoảng trắng thừa
    """
    soup = BeautifulSoup(html, 'html.parser') # phân tích cú pháp HTML
    text = soup.get_text(separator="\n")
    return re.sub(r'\n\n+',"\n\n", text).strip() # Xóa các khoảng trắng thừa và dòng trống thừa
    
def crawl_web(url_data):
    #Tạo loader với độ sâu tối đa là 4 cấp
    loader = RecursiveUrlLoader(
        url=_validate_url(url_data),
        extractor=bs4_extractor,
        metadata_extractor=metadata_extractor,
        max_depth=4,
        exclude_dirs=_crawl_exclude_dirs(url_data),
        prevent_outside=True,
        timeout=20,
        headers=DEFAULT_HEADERS,
        check_response_status=True,
    )
    docs = loader.load()# tải nội dung
    print('length:', len(docs)) # in số lượng tài liệu đã tải
    
    text_splitter = build_text_splitter()
    all_splits = add_chunk_provenance(text_splitter.split_documents(docs))
    print('length_all_split: ', len(all_splits)) # in số lượng đoạn văn bản đã chia nhỏ
    return all_splits

def web_base_loader(url_data, source_name: str | None = None):
    """
    Hàm tải dữ liệu từ một URL dơn (không đệ quy) không chui vào các link con
    Args:
        url_data: str: URL cần tải nội dung
    Returns:
        list: Danh sách các Document đã được chia nhỏ
    """
    loader = WebBaseLoader(
        _validate_url(url_data),
        header_template=DEFAULT_HEADERS,
        raise_for_status=True,
    )
    docs = loader.load()
    print('length:', len(docs)) # in số lượng tài liệu đã tải
    
    text_splitter = build_text_splitter()
    all_splits = add_chunk_provenance(
        text_splitter.split_documents(docs),
        source_name=source_name,
    )
    return all_splits

def save_data_locally(documents, filename, directory):
    """
    Lưu danh sách document vào file JSON
    Args:
        documents: list: Danh sách các Document cần lưu
        filename: str: Tên file JSON cần lưu (vd: data.json)
        directory: str: Thư mục chứa file ( vd: data_v3)
    Returns:
        None: Hàm không trả về giá trị gì chỉ lưu và in thông báo
    """
    if not os.path.exists(directory):
        os.makedirs(directory, exist_ok=True) # tạo thư mục nếu chưa tồn tại
    file_path = os.path.join(directory, filename)
    
    # Chuyển đổi danh sách Document thành danh sách dict để lưu vào JSON
    data_to_save = [
        {
            "page_content": doc.page_content,
            "metadata": doc.metadata
        }
        for doc in documents
    ]
    
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data_to_save, f, ensure_ascii=False, indent=4)
    print(f'Data saved to {file_path}')

def main():
    """
    Hàm chính điều khiển luồng chương trình
    1. Crawl dữ liệu từ web stack-ai
    2. Lưu dữ liệu vào file JSON
    3. In ra kết quả crawl để kiểm tra 
    """
    # llms-full.txt already contains the aggregated documentation. Loading it as
    # a single resource avoids recursively following every link embedded in it.
    data = web_base_loader(
        DEFAULT_DOCUMENTATION_URL,
        source_name="Stack AI Documentation",
    )
    # Lưu dữ liệu vào thư mục data
    save_data_locally(data, "stack_ai.json", "data")
    print(f"Crawled and saved {len(data)} chunks")

if __name__ == "__main__":
    main()
