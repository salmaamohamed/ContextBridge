"""Shared test setup.

Two kinds of tests live in this folder:
  * fast tests  -> fake model + in-memory Qdrant. Run anywhere, in seconds.
  * model tests -> the REAL jina-clip-v2 model (marked @pytest.mark.model).
  * server test -> the REAL Qdrant from docker compose (marked @pytest.mark.server).

    pytest                      # everything (model/server tests skip themselves if unavailable)
    pytest -m "not model"       # fast tests only
"""

import hashlib

import numpy as np
import pytest
from qdrant_client import QdrantClient

from app.config import settings
from app.embeddings import embedder, vector_store
from app.schemas.chunk import ChunkSchema

TEST_COLLECTION = "test_contextbridge_kb"


class FakeModel:
    """Stands in for jina-clip-v2 so fast tests don't need the real model.

    Same input -> same vector (seeded by a hash of the input), so results are
    repeatable. It also records the kwargs it was called with, so tests can
    check e.g. that queries pass task="retrieval.query".
    """

    def __init__(self):
        self.text_calls = []
        self.image_calls = []

    def _vec(self, item, dim):
        seed = int(hashlib.md5(str(item).encode()).hexdigest()[:8], 16)
        return np.random.default_rng(seed).normal(size=dim) * 5  # deliberately NOT length 1

    def encode_text(self, texts, **kwargs):
        self.text_calls.append({"texts": texts, **kwargs})
        return np.array([self._vec("text:" + t, kwargs["truncate_dim"]) for t in texts])

    def encode_image(self, images, **kwargs):
        self.image_calls.append({"images": images, **kwargs})
        return np.array([self._vec("image:" + str(i), kwargs["truncate_dim"]) for i in images])


@pytest.fixture
def fake_model(monkeypatch):
    model = FakeModel()
    monkeypatch.setattr(embedder, "get_model", lambda: model)
    return model


@pytest.fixture
def memory_qdrant(monkeypatch):
    """In-memory Qdrant: behaves like the real one, but lives only for this test."""
    client = QdrantClient(":memory:")
    monkeypatch.setattr(vector_store, "get_client", lambda: client)
    monkeypatch.setattr(settings, "qdrant_collection", TEST_COLLECTION)
    return client


@pytest.fixture
def sample_chunks():
    """One chunk per shape we expect from Salma / Doha."""
    return [
        ChunkSchema(  # department-specific company chunk
            chunk_id="hr_recruiter_0", doc_id="hr_recruiter", source_type="company_kb",
            department="hr", category="roles", topic="recruiter",
            text="The recruiter screens candidates and schedules interviews.",
        ),
        ChunkSchema(  # company-wide chunk (no department)
            chunk_id="policy_remote_0", doc_id="policy_remote", source_type="company_kb",
            category="policies", topic="remote_work",
            text="Employees may work remotely up to three days per week.",
        ),
        ChunkSchema(  # project chunk
            chunk_id="payments_refund_0", doc_id="payments_refund", source_type="project_kb",
            project="payment-platform", category="apis", topic="refund_api",
            text="The refund API reverses a completed payment.",
        ),
        ChunkSchema(  # image chunk
            chunk_id="payments_diagram_0", doc_id="payments_diagram", source_type="project_kb",
            project="payment-platform", category="architecture", topic="diagram",
            text="Payment platform architecture diagram", image_ref="data/diagram.png",
        ),
    ]
