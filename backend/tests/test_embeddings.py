"""Tests for embed_text / embed_image and the Qdrant vector store."""

import numpy as np
import pytest
from qdrant_client.models import FieldCondition, Filter, IsEmptyCondition, MatchValue, PayloadField

from app.config import settings
from app.embeddings import embedder, vector_store
from app.embeddings.embedder import embed_image, embed_text
from app.embeddings.vector_store import count, ensure_collection, point_id, upsert
from app.schemas.chunk import ChunkSchema

DIM = settings.embedding_dim


def _is_unit_length(vec):
    return abs(np.linalg.norm(vec) - 1.0) < 1e-4


def _search(client, query_vec, limit=5, query_filter=None):
    return client.query_points(
        settings.qdrant_collection, query=query_vec, limit=limit, query_filter=query_filter
    ).points


# --------------------------------------------------------------------------
# 1. embedder -- fast tests with the fake model
# --------------------------------------------------------------------------

class TestEmbedder:
    def test_single_string_returns_one_vector(self, fake_model):
        vectors = embed_text("hello")
        assert len(vectors) == 1
        assert len(vectors[0]) == DIM

    def test_list_returns_one_vector_per_text(self, fake_model):
        assert len(embed_text(["a", "b", "c"])) == 3

    def test_empty_input_skips_the_model(self, fake_model):
        assert embed_text([]) == []
        assert embed_image([]) == []
        assert fake_model.text_calls == [] and fake_model.image_calls == []

    def test_vectors_are_normalized(self, fake_model):
        # FakeModel returns long vectors on purpose; _normalize must fix that.
        for vec in embed_text(["a", "b"]) + embed_image(["x.png"]):
            assert _is_unit_length(vec)

    def test_query_mode_passes_retrieval_task(self, fake_model):
        embed_text("how do I get VPN?", is_query=True)
        assert fake_model.text_calls[-1]["task"] == "retrieval.query"

    def test_document_mode_has_no_task(self, fake_model):
        embed_text("VPN access is requested through IT.")
        assert "task" not in fake_model.text_calls[-1]

    def test_single_image_returns_one_vector(self, fake_model):
        vectors = embed_image("diagram.png")
        assert len(vectors) == 1 and len(vectors[0]) == DIM

    def test_normalize_handles_a_single_flat_vector(self):
        # The ndim == 1 case: one flat list becomes a table with one row.
        out = embedder._normalize(np.array([3.0, 4.0]))
        assert out[0] == pytest.approx([0.6, 0.8])

    def test_normalize_handles_zero_vector(self):
        assert embedder._normalize(np.zeros((1, 3))) == [[0.0, 0.0, 0.0]]


# --------------------------------------------------------------------------
# 2. vector store -- fast tests with fake model + in-memory Qdrant
# --------------------------------------------------------------------------

class TestVectorStore:
    def test_point_id_is_stable_and_unique(self):
        assert point_id("chunk_1") == point_id("chunk_1")
        assert point_id("chunk_1") != point_id("chunk_2")

    def test_ensure_collection_creates_it_with_right_size(self, memory_qdrant):
        ensure_collection()
        ensure_collection()  # calling twice must be safe
        info = memory_qdrant.get_collection(settings.qdrant_collection)
        assert info.config.params.vectors.size == DIM

    def test_recreate_wipes_the_collection(self, fake_model, memory_qdrant, sample_chunks):
        upsert(sample_chunks)
        ensure_collection(recreate=True)
        assert count() == 0

    def test_upsert_stores_every_chunk(self, fake_model, memory_qdrant, sample_chunks):
        assert upsert(sample_chunks) == len(sample_chunks)
        assert count() == len(sample_chunks)

    def test_upsert_empty_list(self, fake_model, memory_qdrant):
        assert upsert([]) == 0

    def test_reupsert_does_not_duplicate(self, fake_model, memory_qdrant, sample_chunks):
        upsert(sample_chunks)
        upsert(sample_chunks)
        assert count() == len(sample_chunks)

    def test_reupsert_updates_the_text(self, fake_model, memory_qdrant, sample_chunks):
        upsert(sample_chunks)
        edited = sample_chunks[0].model_copy(update={"text": "Updated recruiter text."})
        upsert([edited])
        point = memory_qdrant.retrieve(settings.qdrant_collection, [point_id(edited.chunk_id)])[0]
        assert point.payload["text"] == "Updated recruiter text."
        assert count() == len(sample_chunks)

    def test_payload_holds_the_full_chunk(self, fake_model, memory_qdrant, sample_chunks):
        upsert(sample_chunks)
        chunk = sample_chunks[0]
        point = memory_qdrant.retrieve(settings.qdrant_collection, [point_id(chunk.chunk_id)])[0]
        assert point.payload == chunk.model_dump()
        # and it can be turned straight back into a ChunkSchema (what Omnia will do)
        assert ChunkSchema(**point.payload) == chunk

    def test_images_go_to_embed_image_and_text_to_embed_text(self, fake_model, memory_qdrant, sample_chunks):
        upsert(sample_chunks)
        assert fake_model.image_calls[0]["images"] == ["data/diagram.png"]
        assert "Payment platform architecture diagram" not in fake_model.text_calls[0]["texts"]
        assert len(fake_model.text_calls[0]["texts"]) == 3

    def test_each_chunk_gets_its_own_vector(self, fake_model, memory_qdrant, sample_chunks):
        # Searching with a chunk's exact vector must return that chunk first,
        # which proves vectors weren't shuffled between text and image chunks.
        upsert(sample_chunks)
        for chunk in sample_chunks:
            vec = embed_image(chunk.image_ref)[0] if chunk.image_ref else embed_text(chunk.text)[0]
            top = _search(memory_qdrant, vec, limit=1)[0]
            assert top.payload["chunk_id"] == chunk.chunk_id

    def test_batching_stores_everything(self, fake_model, memory_qdrant):
        chunks = [
            ChunkSchema(chunk_id=f"c{i}", doc_id="d", source_type="company_kb", text=f"text {i}")
            for i in range(10)
        ]
        assert upsert(chunks, batch_size=3) == 10  # batches of 3,3,3,1
        assert count() == 10

    def test_filter_by_department(self, fake_model, memory_qdrant, sample_chunks):
        upsert(sample_chunks)
        hits = _search(memory_qdrant, embed_text("anything")[0], query_filter=Filter(
            must=[FieldCondition(key="department", match=MatchValue(value="hr"))]))
        assert [h.payload["chunk_id"] for h in hits] == ["hr_recruiter_0"]

    def test_filter_by_project(self, fake_model, memory_qdrant, sample_chunks):
        upsert(sample_chunks)
        hits = _search(memory_qdrant, embed_text("anything")[0], query_filter=Filter(
            must=[FieldCondition(key="project", match=MatchValue(value="payment-platform"))]))
        assert {h.payload["chunk_id"] for h in hits} == {"payments_refund_0", "payments_diagram_0"}

    def test_company_wide_chunks_have_empty_department(self, fake_model, memory_qdrant, sample_chunks):
        # Tells Omnia how to find company-wide docs: department is stored as null.
        upsert(sample_chunks)
        hits = _search(memory_qdrant, embed_text("anything")[0], query_filter=Filter(
            must=[FieldCondition(key="source_type", match=MatchValue(value="company_kb")),
                  IsEmptyCondition(is_empty=PayloadField(key="department"))]))
        assert [h.payload["chunk_id"] for h in hits] == ["policy_remote_0"]


# --------------------------------------------------------------------------
# 3. real model -- does jina-clip-v2 actually understand meaning?
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def real_model():
    try:
        embedder.get_model.cache_clear()
        return embedder.get_model()
    except Exception as e:  # not installed / no network / no disk
        pytest.skip(f"jina-clip-v2 not available: {e}")


@pytest.mark.model
class TestRealModel:
    def test_real_vectors_have_right_shape_and_length(self, real_model):
        vec = embed_text("How do I request VPN access?", is_query=True)[0]
        assert len(vec) == DIM and _is_unit_length(vec)

    def test_similar_meaning_scores_higher(self, real_model):
        q = np.array(embed_text("How do I set up my laptop for development?", is_query=True)[0])
        related, unrelated = map(np.array, embed_text([
            "Install the approved development tools and clone the repository.",
            "The cafeteria serves lunch between 12 and 2 pm.",
        ]))
        assert q @ related > q @ unrelated

    def test_retrieval_on_real_knowledge_base(self, real_model, memory_qdrant):
        """Embed real KB files and check a few questions find the right document."""
        from pathlib import Path

        kb = Path(__file__).resolve().parents[2] / "knowledge_base"
        files = {
            "dev_env_sop": kb / "company/sop/development_environment_setup.txt",
            "remote_work": kb / "company/policies/remote_work.txt",
            "recruitment": kb / "Departments/HR/processes/recruitment_process.txt",
            "code_review": kb / "Departments/software/processes/code_review.txt",
            "docker": kb / "Departments/software/tools/docker.txt",
        }
        if not all(p.exists() for p in files.values()):
            pytest.skip("knowledge_base files not found")

        # one chunk per whole file -- good enough until Salma's chunker lands
        chunks = [
            ChunkSchema(chunk_id=name, doc_id=name, source_type="company_kb", text=path.read_text())
            for name, path in files.items()
        ]
        upsert(chunks)

        questions = {
            "What steps do I follow to prepare my development environment?": "dev_env_sop",
            "Am I allowed to work from home?": "remote_work",
            "How does the company hire new candidates?": "recruitment",
            "What should I check when reviewing a pull request?": "code_review",
        }
        for question, expected in questions.items():
            top = _search(memory_qdrant, embed_text(question, is_query=True)[0], limit=1)[0]
            assert top.payload["chunk_id"] == expected, f"{question!r} -> {top.payload['chunk_id']}"


# --------------------------------------------------------------------------
# 4. real Qdrant server -- the docker compose one
# --------------------------------------------------------------------------

@pytest.mark.server
def test_real_qdrant_server_roundtrip(fake_model, sample_chunks, monkeypatch):
    from qdrant_client import QdrantClient

    client = QdrantClient(url=settings.qdrant_url, timeout=3)
    try:
        client.get_collections()
    except Exception:
        pytest.skip(f"no Qdrant server at {settings.qdrant_url}")

    monkeypatch.setattr(vector_store, "get_client", lambda: client)
    monkeypatch.setattr(settings, "qdrant_collection", "test_contextbridge_kb")
    try:
        ensure_collection(recreate=True)
        assert upsert(sample_chunks) == len(sample_chunks)
        assert count() == len(sample_chunks)
        hits = _search(client, embed_text("anything")[0], query_filter=Filter(
            must=[FieldCondition(key="department", match=MatchValue(value="hr"))]))
        assert [h.payload["chunk_id"] for h in hits] == ["hr_recruiter_0"]
    finally:
        client.delete_collection("test_contextbridge_kb")
