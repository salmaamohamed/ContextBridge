from fastapi import FastAPI

from app.api.v1.endpoints import health

app = FastAPI(title="ContextBridge")

app.include_router(health.router, tags=["health"])
