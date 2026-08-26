import os

import streamlit as st
from dotenv import load_dotenv

from agent import (
    DEFAULT_OPENROUTER_MODEL,
    get_llm_and_agent,
    get_retriever,
    invoke_agent,
)
from crawl import DEFAULT_DOCUMENTATION_URL
from seed_data import seed_milvus, seed_milvus_live


load_dotenv()

MILVUS_URI = os.getenv("MILVUS_URI", "http://localhost:19530")
EMBEDDING_OPTIONS = ("HuggingFace", "Ollama")
LLM_PRESETS = {
    "Gemini 2.5 Flash": "gemini",
    "GPT-5.6 Luna (OpenRouter)": "openrouter",
    "Qwen2.5 7B (Local)": "ollama",
}


def _default_llm_preset() -> str:
    if os.getenv("GOOGLE_API_KEY"):
        return "Gemini 2.5 Flash"
    if os.getenv("OPENROUTER_API_KEY"):
        return "GPT-5.6 Luna (OpenRouter)"
    return "Qwen2.5 7B (Local)"


@st.cache_resource(show_spinner=False, max_entries=12)
def get_cached_agent(
    collection_name: str,
    embedding_choice: str,
    llm_choice: str,
    openrouter_model: str,
):
    use_ollama_embeddings = embedding_choice == "Ollama"
    retriever = get_retriever(
        collection_name,
        use_ollama_embeddings=use_ollama_embeddings,
        milvus_uri=MILVUS_URI,
    )
    return get_llm_and_agent(
        retriever,
        llm_choice=llm_choice,
        openrouter_model=openrouter_model or None,
    )


def handle_local_file(use_ollama_embeddings: bool) -> None:
    with st.form("local_seed_form"):
        collection_name = st.text_input("Tên collection trong Milvus", "data_test")
        filename = st.text_input("Tên file JSON", "stack_ai.json")
        directory = st.text_input("Thư mục chứa file", "data")
        submitted = st.form_submit_button(
            "Tải dữ liệu từ file",
            icon=":material/upload_file:",
        )

    if not submitted:
        return
    if not collection_name.strip():
        st.error("Vui lòng nhập tên collection.")
        return

    with st.spinner("Đang tạo embeddings và cập nhật collection..."):
        try:
            seed_milvus(
                MILVUS_URI,
                collection_name,
                filename,
                directory,
                use_ollama=use_ollama_embeddings,
            )
            get_cached_agent.clear()
            st.success(f"Đã cập nhật collection '{collection_name}' an toàn.")
        except Exception as error:
            st.error(f"Không thể tải dữ liệu: {error}")


def handle_url_input(use_ollama_embeddings: bool) -> None:
    with st.form("url_seed_form"):
        collection_name = st.text_input("Tên collection trong Milvus", "data_test_live")
        url = st.text_input("URL cần crawl", DEFAULT_DOCUMENTATION_URL)
        submitted = st.form_submit_button(
            "Crawl dữ liệu",
            icon=":material/language:",
        )

    if not submitted:
        return
    if not collection_name.strip() or not url.strip():
        st.error("Vui lòng nhập collection và URL.")
        return

    with st.spinner("Đang crawl, tạo embeddings và cập nhật collection..."):
        try:
            seed_milvus_live(
                url,
                MILVUS_URI,
                collection_name,
                "stack-ai",
                use_ollama=use_ollama_embeddings,
            )
            get_cached_agent.clear()
            st.success(f"Đã cập nhật collection '{collection_name}' an toàn.")
        except Exception as error:
            st.error(f"Không thể crawl dữ liệu: {error}")


def setup_sidebar() -> tuple[str, str, str, str]:
    with st.sidebar:
        st.title("Cấu hình")

        embedding_choice = st.segmented_control(
            "Embedding model",
            EMBEDDING_OPTIONS,
            default="HuggingFace",
            key="embedding_choice",
        )
        use_ollama_embeddings = embedding_choice == "Ollama"

        llm_options = tuple(LLM_PRESETS)
        llm_preset = st.selectbox(
            "LLM model",
            llm_options,
            index=llm_options.index(_default_llm_preset()),
            key="llm_choice",
        )
        llm_choice = LLM_PRESETS[llm_preset]
        openrouter_model = (
            DEFAULT_OPENROUTER_MODEL
            if llm_choice == "openrouter"
            else ""
        )

        collection_to_query = st.text_input(
            "Collection để truy vấn",
            "data_test",
            help="Embedding model phải trùng với model đã dùng khi seed collection.",
        ).strip()

        if st.button("Làm mới agent", icon=":material/refresh:"):
            get_cached_agent.clear()
            st.success("Đã xóa agent cache.")

        st.divider()
        st.subheader("Nạp dữ liệu")
        data_source = st.segmented_control(
            "Nguồn dữ liệu",
            ("File local", "URL trực tiếp"),
            default="File local",
            key="data_source",
        )
        if data_source == "File local":
            handle_local_file(use_ollama_embeddings)
        else:
            handle_url_input(use_ollama_embeddings)

        st.divider()
        if st.button("Xóa hội thoại", icon=":material/delete:"):
            st.session_state.messages = []
            st.rerun()

    return llm_choice, collection_to_query, embedding_choice, openrouter_model


def setup_chat_interface(llm_choice: str) -> None:
    st.title("AI Assistant")
    captions = {
        "gemini": "LangChain RAG với Gemini 2.5 Flash",
        "openrouter": "LangChain RAG với GPT-5.6 Luna qua OpenRouter",
        "ollama": "LangChain RAG với Qwen2.5 7B chạy local qua Ollama",
    }
    st.caption(captions[llm_choice])

    st.session_state.setdefault(
        "messages",
        [{"role": "assistant", "content": "Tôi có thể giúp gì cho bạn?"}],
    )
    for message in st.session_state.messages:
        role = "user" if message["role"] == "human" else message["role"]
        with st.chat_message(role):
            st.write(message["content"])


def handle_user_input(
    llm_choice: str,
    collection_name: str,
    embedding_choice: str,
    openrouter_model: str,
) -> None:
    prompt = st.chat_input(
        "Hãy hỏi về dữ liệu đã index",
        submit_mode="disable",
    )
    if not prompt:
        return

    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.write(prompt)

    with st.chat_message("assistant"):
        try:
            with st.spinner("Đang truy xuất dữ liệu và tạo câu trả lời..."):
                agent_executor = get_cached_agent(
                    collection_name,
                    embedding_choice,
                    llm_choice,
                    openrouter_model,
                )
                output = invoke_agent(agent_executor, st.session_state.messages)
        except Exception as error:
            st.error(f"Không thể tạo câu trả lời: {error}")
            return

        st.write(output)
        st.session_state.messages.append({"role": "assistant", "content": output})


def main() -> None:
    st.set_page_config(
        page_title="RAG LangChain",
        page_icon=":material/smart_toy:",
        layout="wide",
    )
    llm_choice, collection_name, embedding_choice, openrouter_model = setup_sidebar()
    setup_chat_interface(llm_choice)

    if not collection_name:
        st.warning("Vui lòng nhập collection để bắt đầu chat.")
        return

    handle_user_input(
        llm_choice,
        collection_name,
        embedding_choice,
        openrouter_model,
    )


if __name__ == "__main__":
    main()
