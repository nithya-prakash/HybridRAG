from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

router = APIRouter(tags=["metrics"])


@router.get("/metrics")
async def metrics() -> Response:
    # Deliberately unauthenticated, matching how Prometheus itself scrapes —
    # it has no session cookie to send. In a real deployment this endpoint
    # is restricted at the network/ingress level (internal-only, or an
    # allowlisted scrape source), not behind the app's own user auth; see
    # ARCHITECTURE.md § Observability.
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
