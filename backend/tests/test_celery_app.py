from app.core.celery_app import _configure_worker_logging, celery_app


def test_configure_worker_logging_signal_handler_runs_without_error():
    # Connecting to Celery's setup_logging signal at all is what disables
    # Celery's own default logging config in favor of this app's structlog
    # setup (see app/core/celery_app.py's module docstring-comment) — the
    # handler itself just needs to call configure_logging() without raising.
    _configure_worker_logging()


def test_ping_and_process_document_tasks_are_registered():
    assert "ping" in celery_app.tasks
    assert "process_document" in celery_app.tasks
