import httpx
import pae_config as config


def get_http_client() -> httpx.Client:
    """
    Single shared httpx client for all orchestrator endpoints.

    In production, REST outputs, PAE inputs, and the SSE stream are all
    served by the same orchestrator on ORCHESTRATOR_BASE_URL.

    All requests are authenticated via the X-API-Key header.
    """
    return httpx.Client(
        base_url=config.ORCHESTRATOR_BASE_URL,
        headers={"X-API-Key": config.ORCHESTRATOR_API_KEY},
        timeout=10.0,
    )
