import os
import unittest
from unittest.mock import Mock, patch

from langchain_core.documents import Document

from backend.app.services.indexing import (
    _documents_from_local_data,
    _embedding_from_description,
    _embedding_model_name,
    _embedding_provider,
    _get_embeddings,
    _temporary_collection_name,
    _validate_collection_name,
    append_documents,
    delete_document_chunks,
)


class SeedDataTests(unittest.TestCase):
    def test_collection_name_validation(self):
        self.assertEqual(_validate_collection_name("data_test_2"), "data_test_2")
        for invalid_name in ("", "2data", "data-test", "data test"):
            with self.subTest(invalid_name=invalid_name):
                with self.assertRaises(ValueError):
                    _validate_collection_name(invalid_name)

    def test_temporary_collection_name_stays_valid_and_bounded(self):
        name = _temporary_collection_name("a" * 255, "staging")
        self.assertLessEqual(len(name), 255)
        self.assertEqual(_validate_collection_name(name), name)

    def test_embedding_marker_is_read_from_description(self):
        description = "RAG documents; embedding_model=ollama:nomic-embed-text"
        self.assertEqual(
            _embedding_from_description(description),
            "ollama:nomic-embed-text",
        )

    def test_embedding_provider_must_be_selected(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "EMBEDDING_PROVIDER must be selected"):
                _embedding_provider(None)

    def test_embedding_provider_can_be_selected_from_environment(self):
        with patch.dict(os.environ, {"EMBEDDING_PROVIDER": "ollama"}, clear=True):
            self.assertEqual(_embedding_provider(None), "ollama")

    def test_all_embedding_providers_can_be_selected(self):
        for provider in ("openrouter", "openai", "gemini", "ollama"):
            with self.subTest(provider=provider):
                with patch.dict(
                    os.environ,
                    {"EMBEDDING_PROVIDER": provider},
                    clear=True,
                ):
                    self.assertEqual(_embedding_provider(), provider)

    def test_openai_embedding_model_is_configurable(self):
        environment = {
            "EMBEDDING_PROVIDER": "openai",
            "OPENAI_API_KEY": "test-key",
            "OPENAI_EMBEDDING_MODEL": "text-embedding-3-large",
        }
        with patch.dict(os.environ, environment, clear=True):
            with patch("backend.app.services.indexing.OpenAIEmbeddings") as factory:
                _get_embeddings(None)
            factory.assert_called_once_with(
                model="text-embedding-3-large",
                api_key="test-key",
            )
            self.assertEqual(
                _embedding_model_name(None),
                "openai:text-embedding-3-large",
            )

    def test_request_can_override_embedding_model_without_changing_environment(self):
        with patch.dict(
            os.environ,
            {"OPENAI_API_KEY": "test-key"},
            clear=True,
        ):
            with patch("backend.app.services.indexing.OpenAIEmbeddings") as factory:
                _get_embeddings("openai", "text-embedding-3-large")
            factory.assert_called_once_with(
                model="text-embedding-3-large",
                api_key="test-key",
            )
            self.assertEqual(
                _embedding_model_name("openai", "text-embedding-3-large"),
                "openai:text-embedding-3-large",
            )

    def test_gemini_embedding_requires_google_api_key(self):
        with patch.dict(
            os.environ,
            {"EMBEDDING_PROVIDER": "gemini"},
            clear=True,
        ):
            with self.assertRaisesRegex(ValueError, "GOOGLE_API_KEY is required"):
                _get_embeddings(None)

    def test_openrouter_embedding_uses_compatible_endpoint(self):
        environment = {
            "EMBEDDING_PROVIDER": "openrouter",
            "OPENROUTER_API_KEY": "test-key",
            "OPENROUTER_EMBEDDING_MODEL": "openai/text-embedding-3-large",
        }
        with patch.dict(os.environ, environment, clear=True):
            with patch("backend.app.services.indexing.OpenAIEmbeddings") as factory:
                _get_embeddings(None)
            factory.assert_called_once_with(
                model="openai/text-embedding-3-large",
                api_key="test-key",
                base_url="https://openrouter.ai/api/v1",
                tiktoken_model_name="text-embedding-3-small",
            )

    def test_empty_documents_are_not_indexed(self):
        documents = _documents_from_local_data(
            [
                {"page_content": "", "metadata": {}},
                {"page_content": "Nội dung", "metadata": {"source": "test"}},
            ],
            "sample",
        )
        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0].page_content, "Nội dung")

    def test_oversized_metadata_is_bounded_for_milvus(self):
        documents = _documents_from_local_data(
            [{"page_content": "Nội dung", "metadata": {"title": "x" * 70_000}}],
            "sample",
        )
        self.assertEqual(len(documents[0].metadata["title"]), 1_000)

    @patch("backend.app.services.indexing.connect_to_milvus")
    @patch("backend.app.services.indexing.MilvusClient")
    def test_append_uses_shared_existing_collection(self, client_factory, connect):
        manager = client_factory.return_value
        manager.has_collection.return_value = True
        vectorstore = Mock()
        vectorstore.client = Mock()
        connect.return_value = vectorstore
        document = Document(
            page_content="Nội dung",
            metadata={
                "document_id": "08d7ee84-c26e-4316-b1ac-ddcfeaac416d",
                "chunk_id": "04b1e8d8-84be-44ef-862c-f5b7e8255cc7",
            },
        )

        count = append_documents("http://milvus:19530", "document_chunks", [document], "ollama")

        self.assertEqual(count, 1)
        vectorstore.add_documents.assert_called_once_with(
            documents=[document],
            ids=["04b1e8d8-84be-44ef-862c-f5b7e8255cc7"],
        )
        vectorstore.client.close.assert_called_once()

    def test_append_requires_document_and_chunk_provenance(self):
        with self.assertRaisesRegex(ValueError, "document_id"):
            append_documents(
                "http://milvus:19530",
                "document_chunks",
                [Document(page_content="Nội dung", metadata={})],
            )

    @patch("backend.app.services.indexing.MilvusClient")
    def test_delete_scopes_filter_to_document_id(self, client_factory):
        client = client_factory.return_value
        client.has_collection.return_value = True
        client.delete.return_value = {"delete_count": 3}
        document_id = "08d7ee84-c26e-4316-b1ac-ddcfeaac416d"

        deleted = delete_document_chunks(
            "http://milvus:19530",
            "document_chunks",
            document_id,
        )

        self.assertEqual(deleted, 3)
        client.delete.assert_called_once_with(
            collection_name="document_chunks",
            filter=f'document_id == "{document_id}"',
        )


if __name__ == "__main__":
    unittest.main()
