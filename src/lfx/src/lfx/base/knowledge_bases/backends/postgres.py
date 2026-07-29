"""Postgres/pgvector backend for Knowledge Bases.

``backend_config`` stores variable names rather than credentials:

* ``connection_url_variable``: variable containing the credential-free
  PostgreSQL URL (defaults to ``POSTGRES_VECTOR_URL``).
* ``username_variable`` / ``password_variable``: optional credential variables
  (defaults to ``POSTGRES_VECTOR_USERNAME`` / ``POSTGRES_VECTOR_PASSWORD``).
* ``collection_name``: optional LangChain collection name. The knowledge-base
  name is used when omitted, keeping different KBs isolated in the shared
  pgvector tables.

The implementation uses LangChain's PGVector schema and a raw SQLAlchemy
session for administrative operations that the VectorStore API does not
provide (streaming, count and storage size).
"""

from __future__ import annotations

import asyncio
import queue as sync_queue
import threading
from typing import TYPE_CHECKING, Any

from lfx.base.knowledge_bases.backends.base import (
    BackendType,
    BaseVectorStoreBackend,
    IngestedDocument,
    NonRetryableBackendError,
    TestConnectionResult,
    drain_queue_until_sentinel,
)
from lfx.log.logger import logger
from lfx.utils.util_strings import sanitize_database_url

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from langchain_core.vectorstores import VectorStore


DEFAULT_CONNECTION_URL_VARIABLE = "POSTGRES_VECTOR_URL"
DEFAULT_USERNAME_VARIABLE = "POSTGRES_VECTOR_USERNAME"
DEFAULT_PASSWORD_VARIABLE = "POSTGRES_VECTOR_PASSWORD"  # noqa: S105 - variable name


class PostgresBackend(BaseVectorStoreBackend):
    """PostgreSQL with the pgvector extension as a Knowledge Base backend."""

    backend_type = BackendType.POSTGRES

    async def _resolve_secrets(self) -> None:
        variable_name = self.backend_config.get("connection_url_variable") or DEFAULT_CONNECTION_URL_VARIABLE
        url = await self.resolve_secret(str(variable_name))
        if not url:
            msg = (
                f"PostgresBackend needs the {variable_name!r} Langflow variable "
                "(or env var of the same name) populated with a PostgreSQL connection URL."
            )
            raise ValueError(msg)
        username_variable = self.backend_config.get("username_variable") or DEFAULT_USERNAME_VARIABLE
        password_variable = self.backend_config.get("password_variable") or DEFAULT_PASSWORD_VARIABLE
        username = await self.resolve_secret(str(username_variable))
        password = await self.resolve_secret(str(password_variable))
        if bool(username) != bool(password):
            msg = "PostgresBackend requires both username and password variables when either credential is configured."
            raise ValueError(msg)

        if username and password:
            try:
                from sqlalchemy.engine import make_url

                parsed_url = make_url(url)
                self._resolved_connection_url = parsed_url.set(
                    username=username,
                    password=password,
                ).render_as_string(hide_password=False)
            except Exception as exc:
                msg = f"Invalid PostgreSQL connection URL: {exc}"
                raise ValueError(msg) from exc
        else:
            # URLs containing credentials remain supported for backwards
            # compatibility, though the split-variable form is preferred.
            self._resolved_connection_url = url

    @property
    def collection_name(self) -> str:
        return str(self.backend_config.get("collection_name") or self.kb_name)

    def _build_vector_store(self) -> VectorStore:
        connection_url = getattr(self, "_resolved_connection_url", None)
        if not connection_url:
            msg = "PostgresBackend.ensure_ready() must be awaited before _build_vector_store."
            raise RuntimeError(msg)

        try:
            from langchain_community.vectorstores import PGVector
        except ImportError as exc:
            msg = (
                "PostgresBackend requires langchain-community, pgvector, SQLAlchemy, "
                "and a PostgreSQL driver. Install the 'pgvector' and 'postgresql' extras."
            )
            raise RuntimeError(msg) from exc

        # The current LangChain community adapter uses SQLAlchemy synchronously.
        # ``use_jsonb`` gives metadata filters predictable PostgreSQL semantics.
        store = PGVector.from_existing_index(
            # The adapter only dereferences this for add/search operations.
            # Administrative reads (chunks/count/delete) can initialize the
            # shared PGVector schema without an embedding model.
            embedding=self.embedding_function,  # type: ignore[arg-type]
            collection_name=self.collection_name,
            connection_string=connection_url,
            use_jsonb=True,
        )
        self._pg_engine = store._bind  # noqa: SLF001 - adapter exposes no public engine
        return store

    def _ensure_store(self) -> Any:
        store = self.vector_store
        if getattr(self, "_pg_engine", None) is None:
            self._pg_engine = store._bind  # noqa: SLF001
        return store

    async def add_documents(self, docs: list[Any]) -> None:
        """Embed and persist documents with explicit response validation."""
        if not docs:
            return
        await self.ensure_ready()
        if self.embedding_function is None:
            msg = "PostgresBackend requires an embedding function."
            raise NonRetryableBackendError(msg)

        texts = [doc.page_content for doc in docs]
        try:
            embeddings = await self.embedding_function.aembed_documents(texts)
        except IndexError as exc:
            msg = (
                "The embedding provider returned an incomplete response while "
                f"embedding {len(texts)} document(s). Check the selected embedding model and credentials."
            )
            logger.error("Postgres pgvector write rejected: %s", msg)
            raise NonRetryableBackendError(msg) from exc

        if len(embeddings) != len(texts):
            msg = (
                f"The embedding provider returned {len(embeddings)} vector(s) "
                f"for {len(texts)} document(s). One vector per document is required."
            )
            logger.error("Postgres pgvector write rejected: %s", msg)
            raise NonRetryableBackendError(msg)
        if any(not embedding for embedding in embeddings):
            msg = "The embedding provider returned an empty embedding vector."
            logger.error("Postgres pgvector write rejected: %s", msg)
            raise NonRetryableBackendError(msg)

        dimensions = {len(embedding) for embedding in embeddings}
        if len(dimensions) != 1:
            msg = f"The embedding provider returned inconsistent vector dimensions: {sorted(dimensions)}."
            logger.error("Postgres pgvector write rejected: %s", msg)
            raise NonRetryableBackendError(msg)

        store = self._ensure_store()
        try:
            await asyncio.to_thread(
                store.add_embeddings,
                texts=texts,
                embeddings=embeddings,
                metadatas=[doc.metadata for doc in docs],
            )
        except IndexError as exc:
            msg = (
                "PGVector rejected the embedding response because it was incomplete. "
                "Check the selected embedding model."
            )
            logger.error("Postgres pgvector write rejected: %s", msg)
            raise NonRetryableBackendError(msg) from exc

    async def count(self) -> int:
        await self.ensure_ready()
        store = self._ensure_store()

        def _count() -> int:
            from sqlalchemy import func, select
            from sqlalchemy.orm import Session

            with Session(self._pg_engine) as session:
                statement = (
                    select(func.count(store.EmbeddingStore.uuid))
                    .join(store.CollectionStore)
                    .where(store.CollectionStore.name == self.collection_name)
                )
                return int(session.scalar(statement) or 0)

        return await asyncio.to_thread(_count)

    async def iter_documents(
        self,
        *,
        batch_size: int = 5000,
        include_embeddings: bool = False,
    ) -> AsyncIterator[list[IngestedDocument]]:
        if batch_size <= 0:
            msg = "batch_size must be greater than 0."
            raise ValueError(msg)
        await self.ensure_ready()
        store = self._ensure_store()
        sentinel = object()
        batch_queue: sync_queue.Queue[Any] = sync_queue.Queue(maxsize=2)
        cancel_event = threading.Event()

        def _put_cancelable(item: Any) -> bool:
            while not cancel_event.is_set():
                try:
                    batch_queue.put(item, timeout=0.05)
                except sync_queue.Full:
                    continue
                return True
            return False

        def _stream() -> None:
            try:
                from sqlalchemy import select
                from sqlalchemy.orm import Session

                columns = [
                    store.EmbeddingStore.document,
                    store.EmbeddingStore.cmetadata,
                ]
                if include_embeddings:
                    columns.append(store.EmbeddingStore.embedding)
                statement = (
                    select(*columns)
                    .join(store.CollectionStore)
                    .where(store.CollectionStore.name == self.collection_name)
                    .execution_options(stream_results=True, yield_per=batch_size)
                )
                with Session(self._pg_engine) as session:
                    result = session.execute(statement)
                    while not cancel_event.is_set():
                        rows = result.fetchmany(batch_size)
                        if not rows:
                            break
                        batch = []
                        for row in rows:
                            raw_embedding = row[2] if include_embeddings else None
                            batch.append(
                                IngestedDocument(
                                    content=str(row[0] or ""),
                                    metadata=dict(row[1] or {}),
                                    embedding=list(raw_embedding) if raw_embedding is not None else None,
                                )
                            )
                        if not _put_cancelable(batch):
                            break
            except Exception as exc:  # noqa: BLE001
                if not cancel_event.is_set():
                    _put_cancelable(exc)
            finally:
                batch_queue.put(sentinel)

        worker = asyncio.create_task(asyncio.to_thread(_stream))
        sentinel_seen = False
        try:
            while True:
                item = await asyncio.to_thread(batch_queue.get)
                if item is sentinel:
                    sentinel_seen = True
                    break
                if isinstance(item, Exception):
                    await asyncio.to_thread(batch_queue.get)
                    sentinel_seen = True
                    raise item
                yield item
        finally:
            cancel_event.set()
            if not sentinel_seen:
                await asyncio.to_thread(drain_queue_until_sentinel, batch_queue, sentinel)
            await worker

    async def delete_by(self, where: dict[str, Any]) -> None:
        if not where:
            return
        await self.ensure_ready()
        store = self._ensure_store()

        def _delete() -> None:
            from sqlalchemy import delete, select
            from sqlalchemy.orm import Session

            with Session(self._pg_engine) as session:
                collection_id = session.scalar(
                    select(store.CollectionStore.uuid).where(store.CollectionStore.name == self.collection_name)
                )
                if collection_id is None:
                    return
                statement = delete(store.EmbeddingStore).where(
                    store.EmbeddingStore.collection_id == collection_id,
                    store.EmbeddingStore.cmetadata.contains(where),
                )
                session.execute(statement)
                session.commit()

        await asyncio.to_thread(_delete)

    async def storage_size_bytes(self) -> int:
        """Return the logical bytes occupied by this collection's rows."""
        await self.ensure_ready()
        self._ensure_store()

        def _size() -> int:
            from sqlalchemy import text

            statement = text(
                """
                SELECT COALESCE(SUM(pg_column_size(e)), 0)
                FROM langchain_pg_embedding AS e
                JOIN langchain_pg_collection AS c ON c.uuid = e.collection_id
                WHERE c.name = :collection_name
                """
            )
            with self._pg_engine.connect() as connection:
                return int(connection.scalar(statement, {"collection_name": self.collection_name}) or 0)

        try:
            return await asyncio.to_thread(_size)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Postgres storage size query failed for %s: %s", self.kb_name, exc)
            return 0

    async def test_connection(self) -> TestConnectionResult:
        try:
            await self.ensure_ready()

            def _probe() -> tuple[str, str]:
                from sqlalchemy import create_engine, text

                engine = create_engine(self._resolved_connection_url)
                try:
                    with engine.connect() as connection:
                        version = str(connection.scalar(text("SHOW server_version")) or "")
                        extension = str(
                            connection.scalar(
                                text("SELECT default_version FROM pg_available_extensions WHERE name = 'vector'")
                            )
                            or ""
                        )
                finally:
                    engine.dispose()
                if not extension:
                    msg = "Connected to PostgreSQL, but the pgvector extension is not available on this server."
                    raise RuntimeError(msg)
                return version, extension

            version, extension = await asyncio.to_thread(_probe)
        except ValueError as exc:
            logger.warning("Postgres connection configuration is invalid: %s", exc)
            return TestConnectionResult(ok=False, message=str(exc), details={"type": "ConfigError"})
        except Exception as exc:  # noqa: BLE001
            raw_message = str(exc) or type(exc).__name__
            resolved_url = getattr(self, "_resolved_connection_url", "")
            safe_url = sanitize_database_url(resolved_url)
            safe_message = raw_message.replace(resolved_url, safe_url) if resolved_url else raw_message
            logger.warning(
                "Postgres pgvector connection test failed (target=%s, error_type=%s): %s",
                safe_url or "<unresolved>",
                type(exc).__name__,
                safe_message,
            )
            if "password authentication failed" in raw_message.lower():
                return TestConnectionResult(
                    ok=False,
                    message=(
                        "PostgreSQL password authentication failed. Check the saved username and password variables."
                    ),
                    details={"type": "AuthenticationError", "error": safe_message},
                )
            return TestConnectionResult(
                ok=False,
                message=safe_message,
                details={"type": type(exc).__name__},
            )
        return TestConnectionResult(
            ok=True,
            message="Connected to PostgreSQL with pgvector",
            details={"server_version": version, "pgvector_version": extension},
        )

    async def delete_collection(self) -> None:
        await self.ensure_ready()
        store = self._ensure_store()
        await asyncio.to_thread(store.delete_collection)

    async def teardown(self) -> None:
        engine = getattr(self, "_pg_engine", None)
        if engine is not None and hasattr(engine, "dispose"):
            try:
                await asyncio.to_thread(engine.dispose)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Postgres engine disposal failed: %s", exc)
        self._pg_engine = None
        self._vector_store = None
