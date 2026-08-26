import os
from typing import Any, Iterable

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_classic.retrievers import EnsembleRetriever
from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document
from langchain_core.tools import create_retriever_tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI

from seed_data import connect_to_milvus


load_dotenv()

DEFAULT_MILVUS_URI = "http://localhost:19530"
DEFAULT_OPENROUTER_MODEL = "openai/gpt-5.6-luna"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
BM25_DOCUMENT_LIMIT = 5_000
SUPPORTED_LLM_PROVIDERS = {"gemini", "ollama", "openrouter"}


def _documents_for_bm25(vectorstore: Any) -> list[Document]:
    """Load documents directly instead of vector-searching an empty query."""
    rows = vectorstore.client.query(
        collection_name=vectorstore.collection_name,
        filter="",
        output_fields=["*"],
        limit=BM25_DOCUMENT_LIMIT,
    )

    documents: list[Document] = []
    for row in rows:
        data = dict(row)
        page_content = data.pop(vectorstore._text_field, "")
        data.pop(vectorstore._primary_field, None)

        vector_fields = vectorstore._vector_field
        if isinstance(vector_fields, str):
            vector_fields = [vector_fields]
        for vector_field in vector_fields:
            data.pop(vector_field, None)

        if vectorstore._metadata_field:
            metadata = data.pop(vectorstore._metadata_field, {}) or {}
        else:
            metadata = data

        if page_content:
            documents.append(Document(page_content=page_content, metadata=metadata))

    return documents


def get_retriever(
    collection_name: str = "data_test",
    use_ollama_embeddings: bool = False,
    milvus_uri: str | None = None,
) -> EnsembleRetriever:
    """Create a retriever using the same embedding provider as the collection."""
    vectorstore = connect_to_milvus(
        milvus_uri or os.getenv("MILVUS_URI", DEFAULT_MILVUS_URI),
        collection_name,
        use_ollama=use_ollama_embeddings,
    )
    documents = _documents_for_bm25(vectorstore)
    if not documents:
        raise ValueError(f"Collection '{collection_name}' does not contain documents")

    milvus_retriever = vectorstore.as_retriever(
        search_type="similarity",
        search_kwargs={"k": 4},
    )
    bm25_retriever = BM25Retriever.from_documents(documents)
    bm25_retriever.k = 4

    return EnsembleRetriever(
        retrievers=[milvus_retriever, bm25_retriever],
        weights=[0.7, 0.3],
    )


def _required_env(name: str, provider: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"{name} is required when using {provider}")
    return value


def create_llm(llm_choice: str, openrouter_model: str | None = None) -> Any:
    """Build the selected LLM without requiring credentials for other providers."""
    provider = llm_choice.strip().lower()
    if provider not in SUPPORTED_LLM_PROVIDERS:
        raise ValueError(f"Unsupported LLM provider: {llm_choice}")

    if provider == "gemini":
        return ChatGoogleGenerativeAI(
            model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
            temperature=0,
            streaming=True,
            google_api_key=_required_env("GOOGLE_API_KEY", "Gemini"),
        )

    if provider == "ollama":
        return ChatOllama(
            model=os.getenv("OLLAMA_CHAT_MODEL", "qwen2.5:7b"),
            temperature=0,
            streaming=True,
        )

    headers: dict[str, str] = {}
    if site_url := os.getenv("OPENROUTER_SITE_URL"):
        headers["HTTP-Referer"] = site_url
    if app_name := os.getenv("OPENROUTER_APP_NAME"):
        headers["X-OpenRouter-Title"] = app_name

    return ChatOpenAI(
        model=(openrouter_model or os.getenv("OPENROUTER_MODEL") or DEFAULT_OPENROUTER_MODEL),
        api_key=_required_env("OPENROUTER_API_KEY", "OpenRouter"),
        base_url=OPENROUTER_BASE_URL,
        default_headers=headers or None,
        temperature=0,
        streaming=True,
    )


def get_llm_and_agent(
    retriever: Any,
    llm_choice: str = "gemini",
    openrouter_model: str | None = None,
) -> Any:
    """Create a LangChain 1.x agent with a retrieval tool."""
    tool = create_retriever_tool(
        retriever,
        "find_stack_ai_information",
        "Search the indexed Stack AI documentation for facts relevant to the question.",
    )
    system_prompt = (
        "You are ChatbotAI, an AI assistant for Stack AI documentation. "
        "Use the retrieval tool before answering factual questions about Stack AI. "
        "Base answers on retrieved content and say when the indexed data is insufficient."
    )
    return create_agent(
        model=create_llm(llm_choice, openrouter_model=openrouter_model),
        tools=[tool],
        system_prompt=system_prompt,
    )


def _message_content_as_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and isinstance(block.get("text"), str):
                parts.append(block["text"])
        return "\n".join(parts).strip()
    return str(content)


def invoke_agent(agent_executor: Any, messages: Iterable[dict[str, str]]) -> str:
    """Invoke a LangChain 1.x agent and return the final assistant text."""
    normalized_messages = []
    for message in messages:
        role = "user" if message.get("role") == "human" else message.get("role")
        if role not in {"system", "user", "assistant"}:
            raise ValueError(f"Unsupported message role: {role}")
        normalized_messages.append({"role": role, "content": message.get("content", "")})

    response = agent_executor.invoke({"messages": normalized_messages})
    response_messages = response.get("messages")
    if not response_messages:
        raise RuntimeError("The agent returned no messages")

    output = _message_content_as_text(response_messages[-1].content)
    if not output:
        raise RuntimeError("The agent returned an empty response")
    return output
