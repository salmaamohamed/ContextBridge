from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health_check():
    """Proves the API container is up and can be reached."""
    return {"status": "ok"}
