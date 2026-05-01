import httpx
from app.config.settings import settings

def get_http_client() -> httpx.Client:
    """Single client for all orchestrator endpoints (REST and SSE inputs).
    In production, REST outputs, PAE inputs, and the SSE stream are all
    served by the same orchestrator on ORCHESTRATOR_BASE_URL.
    """
    return httpx.Client(
        base_url=settings.ORCHESTRATOR_BASE_URL,
        headers={"X-API-Key": settings.ORCHESTRATOR_API_KEY},
        timeout=10.0,
    )
