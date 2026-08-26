import os
import re
import json
from urllib.parse import urlparse

os.environ.setdefault("USER_AGENT", "RAG-LangChain/1.0")

from langchain_community.document_loaders import RecursiveUrlLoader, WebBaseLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from bs4 import BeautifulSoup


DEFAULT_HEADERS = {"User-Agent": os.environ["USER_AGENT"]}
DEFAULT_DOCUMENTATION_URL = "https://docs.stackai.com/llms-full.txt"
CRAWL_EXCLUDED_PATHS = ("~gitbook/image", "spaces/", "files/")


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

def bs4_extractor( html:str) -> str:
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
    
    #chia nhỏ văn bản thành các đoạn 1000 ký tự với chồng lấp 500 ký tự
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=500,
        
    )
    all_splits = text_splitter.split_documents(docs)
    print('length_all_split: ', len(all_splits)) # in số lượng đoạn văn bản đã chia nhỏ
    return all_splits

def web_base_loader(url_data):
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
    
    #chia nhỏ văn bản thành các đoạn 1000 ký tự với chồng lấp 500 ký tự
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=500,
        
    )
    all_splits = text_splitter.split_documents(docs)
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
    # Crawl dữ liệu từ web stack-ai
    data = crawl_web(DEFAULT_DOCUMENTATION_URL)
    # Lưu dữ liệu vào thư mục data
    save_data_locally(data, "stack_ai.json", "data")
    print(f"Crawled and saved {len(data)} chunks")

if __name__ == "__main__":
    main()
