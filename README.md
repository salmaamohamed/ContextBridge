# ContextBridge

Agentic AI platform connecting employees with company knowledge, project/task
context, and human expertise.


Infra + Company/Project KB ingestion + embeddings + vector DB + retrieval
evaluation. See `docs/architecture-decisions/` for the reasoning behind each
technology choice.

## Getting started

```bash
cd infra
cp .env.example ../backend/.env
docker-compose up --build
```

Once running, confirm the API is alive:

```bash
curl http://localhost:8000/health
# {"status": "ok"}
```

## Repo layout

```
backend/app/
├── schemas/chunk.py       # the shared contract every track builds against
├── ingestion/             # Company KB + Project KB parsing & chunking
├── embeddings/            # jina-clip-v2 wrapper + Qdrant vector store
├── retrieval/             # top-k search + metadata filtering
└── evaluation/            # golden Q&A sets + retrieval metrics

data/
├── company_kb/departments/<dept>/{roles,processes,tools,onboarding_tasks}/
└── project_kb/projects/<project>/...

infra/
└── docker-compose.yml     # postgres + redis + qdrant + api + worker
```

## Stack

| Layer | Choice |
|---|---|
| API | FastAPI |
| Relational DB | PostgreSQL |
| Cache / queue | Redis + Celery |
| Vector DB | Qdrant |
| Embeddings | jina-clip-v2 (text + image, unified space, self-hosted) |
| Parsing | `unstructured` |
| Containerization | Docker Compose |
