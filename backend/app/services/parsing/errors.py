class ParsingError(Exception):
    """Raised when a stored file can't be parsed — corrupt, truncated, or not
    actually the format its extension/magic bytes claimed. Left to propagate out
    of the Celery task, where it's handled by the existing retry/on_failure
    scaffolding (see app/tasks/document_processing.py)."""
