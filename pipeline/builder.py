import uuid


def make_request_id() -> str:
    """Generate a unique request ID for a new track."""
    return f"track-{uuid.uuid4().hex[:6]}"
