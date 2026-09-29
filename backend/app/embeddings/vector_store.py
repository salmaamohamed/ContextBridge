"""Qdrant storage for ChunkSchema objects: one collection, one vector per chunk,
and the full chunk (text + metadata) stored as the payload.

Usage:
    from app.embeddings.vector_store import ensure_collection, upsert
    ensure_collection()
    upsert(chunks)   # list[ChunkSchema] from Salma / Doha's ingestion
"""

import uuid
from functools import lru_cache
from typing import Sequence

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PayloadSchemaType, PointStruct, VectorParams

from app.config import settings
from app.embeddings.embedder import embed_image, embed_text
from app.schemas.chunk import ChunkSchema

# Fields Omnia filters on -> indexed so filtered search stays fast.
INDEXED_FIELDS = ("source_type", "department", "project", "category", "topic", "doc_id")

# Fixed namespace so the same chunk_id always maps to the same Qdrant point id.
_POINT_NAMESPACE = uuid.UUID("6f1c2a3e-8b4d-4c1e-9a7f-2d5e8c0b1a44")


@lru_cache(maxsize=1)
def get_client() -> QdrantClient:
    return QdrantClient(url=settings.qdrant_url)


def point_id(chunk_id: str) -> str:
    """Qdrant only accepts int/UUID ids, so derive a stable UUID from chunk_id.
    Re-ingesting the same chunk overwrites its point instead of duplicating it."""
    return str(uuid.uuid5(_POINT_NAMESPACE, chunk_id))


def ensure_collection(recreate: bool = False) -> None:
    client = get_client()
    name = settings.qdrant_collection

    if recreate and client.collection_exists(name):
        client.delete_collection(name)

    if not client.collection_exists(name):
        client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(size=settings.embedding_dim, distance=Distance.COSINE),
        )
        for field in INDEXED_FIELDS:
            client.create_payload_index(
                collection_name=name,
                field_name=field,
                field_schema=PayloadSchemaType.KEYWORD,
            )


def _embed_chunks(chunks: Sequence[ChunkSchema]) -> list[list[float]]:
    """Image chunks go through embed_image, everything else through embed_text.
    Both land in the same vector space, so order is all we need to preserve."""
    vectors: list[list[float] | None] = [None] * len(chunks)

    text_idx = [i for i, c in enumerate(chunks) if not c.image_ref]
    image_idx = [i for i, c in enumerate(chunks) if c.image_ref]

    if text_idx:
        for i, v in zip(text_idx, embed_text([chunks[i].text for i in text_idx])):
            vectors[i] = v
    if image_idx:
        for i, v in zip(image_idx, embed_image([chunks[i].image_ref for i in image_idx])):
            vectors[i] = v

    return vectors  # type: ignore[return-value]


def upsert(chunks: Sequence[ChunkSchema], batch_size: int = 64) -> int:
    """Embed and store chunks. Returns how many points were written."""
    if not chunks:
        return 0

    ensure_collection()
    client = get_client()
    written = 0

    for start in range(0, len(chunks), batch_size):
        batch = chunks[start:start + batch_size]
        vectors = _embed_chunks(batch)
        points = [
            PointStruct(
                id=point_id(chunk.chunk_id),
                vector=vector,
                payload=chunk.model_dump(),  # full chunk: text, doc_id, department, project, ...
            )
            for chunk, vector in zip(batch, vectors)
        ]
        client.upsert(collection_name=settings.qdrant_collection, points=points, wait=True)
        written += len(points)

    return written


def count() -> int:
    return get_client().count(settings.qdrant_collection, exact=True).count
