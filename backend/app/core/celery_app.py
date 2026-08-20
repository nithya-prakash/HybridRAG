import asyncio

from celery import Celery
from celery.signals import setup_logging, worker_ready

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "rag_worker",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)


@setup_logging.connect
def _configure_worker_logging(**kwargs) -> None:
    # Connecting to this signal tells Celery "don't set up your own default
    # logging — I'm doing it myself." Without it, the worker process never
    # calls configure_logging() at all (nothing else in its import chain
    # does either — see app/main.py, which only the API process imports),
    # so every task log would go out through Celery's own plain-text
    # formatter, not structlog, and would never carry request_id/task_id
    # context — silently defeating the whole point of Phase 7's log tracing.
    from app.core.logging import configure_logging

    configure_logging()


@worker_ready.connect
def _warm_up_embedding_backend(**kwargs) -> None:
    # Same reasoning as app/main.py's lifespan: pay the local embedding
    # model's load cost once, at worker startup, rather than inside
    # whichever upload happens to be processed first. A no-op for the
    # OpenAI backend. Fires once, before this process starts consuming
    # tasks, so a plain asyncio.run() here is safe — there's no other event
    # loop in this process yet to conflict with.
    from app.core.embeddings import get_embedding_backend

    asyncio.run(get_embedding_backend().warm_up())

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)


@celery_app.task(name="ping")
def ping() -> str:
    return "pong"


# Import task modules so they register with celery_app when the worker starts.
# Placed after `celery_app` is defined to avoid a circular import at module load.
from app.tasks import document_processing  # noqa: E402,F401
