"""ChromaDB persistence. Stores vectors and their metadata; nothing else."""

from __future__ import annotations

from typing import Any

from app.config import settings
from app.ingestion.metadata import MetadataValue


class ChromaVectorStore:
    def __init__(
        self, persist_directory: str, collection_name: str, distance_metric: str
    ) -> None:
        self._persist_directory = persist_directory
        self._collection_name = collection_name
        self._distance_metric = distance_metric
        self._collection: Any | None = None

    def _ensure_collection(self) -> Any:
        if self._collection is None:
            import chromadb

            client = chromadb.PersistentClient(path=self._persist_directory)
            self._collection = client.get_or_create_collection(
                name=self._collection_name,
                metadata={"hnsw:space": self._distance_metric},
            )
        return self._collection

    def add(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict[str, MetadataValue]],
    ) -> None:
        self._ensure_collection().add(
            ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas
        )

    def query(
        self,
        embedding: list[float],
        n_results: int,
        where: dict[str, MetadataValue],
    ) -> list[tuple[str, float]]:
        """Return ``(chunk_id, similarity)`` ordered best-first.

        ``where`` is applied by Chroma before the nearest-neighbour cut, so a
        filtered query returns the best matches *within* the filter rather than
        the filtered remains of a global top-N.
        """
        result = self._ensure_collection().query(
            query_embeddings=[embedding],
            n_results=n_results,
            where=where,
            include=["distances"],
        )
        ids = result["ids"][0]
        distances = result["distances"][0]
        return [(chunk_id, 1.0 - dist) for chunk_id, dist in zip(ids, distances)]

    def delete_document(self, document_id: str) -> None:
        self._ensure_collection().delete(where={"document_id": document_id})

    def count(self) -> int:
        return self._ensure_collection().count()


vector_store = ChromaVectorStore(
    persist_directory=str(settings.CHROMA_DIR),
    collection_name=settings.CHROMA_COLLECTION_NAME,
    distance_metric=settings.CHROMA_DISTANCE_METRIC,
)
