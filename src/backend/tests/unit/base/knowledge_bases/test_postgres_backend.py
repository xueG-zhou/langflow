from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.documents import Document
from lfx.base.knowledge_bases.backends.base import NonRetryableBackendError
from lfx.base.knowledge_bases.backends.postgres import PostgresBackend
from sqlalchemy.exc import OperationalError


@pytest.mark.asyncio
async def test_resolves_split_credentials_into_connection_url(tmp_path):
    backend = PostgresBackend(
        kb_name="my-kb",
        kb_path=tmp_path,
        backend_config={
            "connection_url_variable": "PG_URL",
            "username_variable": "PG_USER",
            "password_variable": "PG_PASSWORD",
        },
    )
    backend.resolve_secret = AsyncMock(
        side_effect={
            "PG_URL": "postgresql+psycopg://db.example.com:5432/vectors",
            "PG_USER": "user@example.com",
            "PG_PASSWORD": "p@ss/word",
        }.get
    )

    await backend.ensure_ready()

    assert backend._resolved_connection_url == (
        "postgresql+psycopg://user%40example.com:p%40ss%2Fword@db.example.com:5432/vectors"
    )


@pytest.mark.asyncio
async def test_rejects_partial_credentials(tmp_path):
    backend = PostgresBackend(kb_name="kb", kb_path=tmp_path)
    backend.resolve_secret = AsyncMock(side_effect=["postgresql+psycopg://db/vectors", "postgres", None])

    with pytest.raises(ValueError, match="both username and password"):
        await backend.ensure_ready()


def test_builds_pgvector_with_kb_name_as_collection(tmp_path):
    embedding = MagicMock()
    backend = PostgresBackend(
        kb_name="my-kb",
        kb_path=tmp_path,
        embedding_function=embedding,
    )
    backend._resolved_connection_url = "postgresql+psycopg://db/vectors"
    store = MagicMock()

    with patch(
        "langchain_community.vectorstores.PGVector.from_existing_index",
        return_value=store,
    ) as factory:
        assert backend._build_vector_store() is store

    factory.assert_called_once_with(
        embedding=embedding,
        collection_name="my-kb",
        connection_string="postgresql+psycopg://db/vectors",
        use_jsonb=True,
    )


def test_uses_configured_collection_name(tmp_path):
    backend = PostgresBackend(
        kb_name="my-kb",
        kb_path=tmp_path,
        backend_config={"collection_name": "shared_collection"},
    )

    assert backend.collection_name == "shared_collection"


def test_builds_store_without_embedding_for_administrative_reads(tmp_path):
    backend = PostgresBackend(kb_name="kb", kb_path=tmp_path)
    backend._resolved_connection_url = "postgresql+psycopg://db/vectors"
    store = MagicMock()

    with patch(
        "langchain_community.vectorstores.PGVector.from_existing_index",
        return_value=store,
    ) as factory:
        assert backend._build_vector_store() is store

    factory.assert_called_once_with(
        embedding=None,
        collection_name="kb",
        connection_string="postgresql+psycopg://db/vectors",
        use_jsonb=True,
    )


@pytest.mark.asyncio
async def test_connection_reports_authentication_failure_without_credentials(tmp_path):
    backend = PostgresBackend(kb_name="kb", kb_path=tmp_path)
    backend._resolved_connection_url = "postgresql+psycopg://user:secret@db/vectors"
    backend._secrets_resolved = True
    error = OperationalError(
        "connection",
        {},
        Exception('FATAL: password authentication failed for user "user"'),
    )

    with patch("sqlalchemy.create_engine", side_effect=error):
        result = await backend.test_connection()

    assert result.ok is False
    assert result.message == (
        "PostgreSQL password authentication failed. Check the saved username and password variables."
    )
    assert result.details["type"] == "AuthenticationError"
    assert "secret" not in result.details["error"]


@pytest.mark.asyncio
async def test_add_documents_rejects_short_embedding_response(tmp_path):
    embedding = MagicMock()
    embedding.aembed_documents = AsyncMock(return_value=[])
    backend = PostgresBackend(
        kb_name="kb",
        kb_path=tmp_path,
        embedding_function=embedding,
    )
    backend._secrets_resolved = True

    with pytest.raises(NonRetryableBackendError, match="returned 0 vector"):
        await backend.add_documents([Document(page_content="hello")])


@pytest.mark.asyncio
async def test_add_documents_writes_validated_embeddings(tmp_path):
    embedding = MagicMock()
    embedding.aembed_documents = AsyncMock(return_value=[[0.1, 0.2]])
    store = MagicMock()
    backend = PostgresBackend(
        kb_name="kb",
        kb_path=tmp_path,
        embedding_function=embedding,
    )
    backend._secrets_resolved = True
    backend._vector_store = store
    backend._pg_engine = MagicMock()
    document = Document(page_content="hello", metadata={"source": "test"})

    await backend.add_documents([document])

    store.add_embeddings.assert_called_once_with(
        texts=["hello"],
        embeddings=[[0.1, 0.2]],
        metadatas=[{"source": "test"}],
    )
