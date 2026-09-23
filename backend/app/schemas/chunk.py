from typing import Literal, Optional

from pydantic import BaseModel, Field


class ChunkSchema(BaseModel):
    """The shared contract between ingestion, embeddings, and retrieval.

    Ingestion (Salma / Doha) produces these.
    Embeddings (Mahmoud) consumes these and writes vectors to Qdrant.
    Retrieval / evaluation (Sara) queries against what embeddings wrote.

    department/category/topic are derived automatically from the source
    file's folder path (see docs/architecture-decisions) — no manual
    tagging required for the KnowledgeBase content.
    """

    chunk_id: str
    doc_id: str
    source_type: Literal["company_kb", "project_kb"]

    # company_kb fields (derived from departments/<dept>/<category>/<file>.txt)
    department: Optional[str] = None       # e.g. "software", "data", "hr"
    category: Optional[str] = None         # e.g. "roles", "processes", "tools", "onboarding_tasks", "overview"
    topic: Optional[str] = None            # filename stem, e.g. "backend_engineer"

    # project_kb fields (mirrors the same idea, one level of nesting different)
    project: Optional[str] = None          # e.g. "payment-platform"

    text: str
    image_ref: Optional[str] = None        # set only for image-derived chunks

    metadata: dict = Field(default_factory=dict)
