import httpx
from config.settings import settings

def get_http_client() -> httpx.Client:
    return httpx.Client(
        base_url=settings.ORCHESTRATOR_BASE_URL,
        headers={"X-API-Key": settings.ORCHESTRATOR_API_KEY},
        timeout=10.0,
    )
