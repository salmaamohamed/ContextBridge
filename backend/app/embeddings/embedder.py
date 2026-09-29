"""jina-clip-v2 wrapper: turns text and images into vectors in ONE shared space.

Because text and images share the same space, a text query can retrieve an
image chunk (and vice versa) -- so the Qdrant collection needs only one vector.

Usage:
    embed_text(["chunk text ..."])                  # documents / chunks
    embed_text("how do I get VPN access?", is_query=True)   # user queries (Omnia)
    embed_image(["data/.../diagram.png"])           # local paths, URLs, or PIL images
"""

from functools import lru_cache
from typing import Sequence, Union

import numpy as np
import torch
from PIL import Image
from transformers import AutoModel

from app.config import settings

ImageInput = Union[str, Image.Image]


def _pick_device() -> str:
    if settings.embedding_device != "auto":
        return settings.embedding_device
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


@lru_cache(maxsize=1)
def get_model():
    """Load the model once per process and reuse it (first call downloads ~2GB)."""
    model = AutoModel.from_pretrained(settings.embedding_model, trust_remote_code=True)
    model.to(_pick_device())
    model.eval()
    return model


def _normalize(vectors: np.ndarray) -> list[list[float]]:
    vectors = np.asarray(vectors, dtype=np.float32)
    if vectors.ndim == 1:
        vectors = vectors[None, :]
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (vectors / norms).tolist()


def embed_text(
    texts: Union[str, Sequence[str]],
    is_query: bool = False,
    batch_size: int | None = None,
) -> list[list[float]]:
    """Embed one or many texts. Always returns a list of vectors.

    is_query=True applies jina's retrieval.query prompt -- use it for user
    questions only, never for the chunks being stored.
    """
    if isinstance(texts, str):
        texts = [texts]
    if not texts:
        return []

    kwargs = {
        "truncate_dim": settings.embedding_dim,
        "batch_size": batch_size or settings.embedding_batch_size,
    }
    if is_query:
        kwargs["task"] = "retrieval.query"

    with torch.inference_mode():
        vectors = get_model().encode_text(list(texts), **kwargs)
    return _normalize(vectors)


def embed_image(
    images: Union[ImageInput, Sequence[ImageInput]],
    batch_size: int | None = None,
) -> list[list[float]]:
    """Embed one or many images (local file paths, URLs, or PIL images)."""
    if isinstance(images, (str, Image.Image)):
        images = [images]
    if not images:
        return []

    with torch.inference_mode():
        vectors = get_model().encode_image(
            list(images),
            truncate_dim=settings.embedding_dim,
            batch_size=batch_size or settings.embedding_batch_size,
        )
    return _normalize(vectors)
