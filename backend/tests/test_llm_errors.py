import httpx
import openai
from qdrant_client.http.exceptions import ResponseHandlingException

from app.core.llm_errors import GENERIC_MESSAGE, classify_llm_error

_REQUEST = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")


def _status_error(cls, status_code: int, body: dict) -> openai.APIStatusError:
    response = httpx.Response(status_code, request=_REQUEST)
    return cls(cls.__name__, response=response, body=body)


def test_authentication_error_is_actionable_about_the_api_key():
    exc = _status_error(
        openai.AuthenticationError,
        401,
        {"code": "invalid_api_key", "type": "invalid_request_error"},
    )

    message = classify_llm_error(exc)

    assert "OPENAI_API_KEY" in message
    assert message != GENERIC_MESSAGE


def test_rate_limit_error_with_insufficient_quota_mentions_billing():
    exc = _status_error(
        openai.RateLimitError, 429, {"code": "insufficient_quota", "type": "insufficient_quota"}
    )

    message = classify_llm_error(exc)

    assert "quota" in message.lower()
    assert "billing" in message.lower()


def test_rate_limit_error_without_insufficient_quota_mentions_retrying():
    exc = _status_error(
        openai.RateLimitError, 429, {"code": "rate_limit_exceeded", "type": "requests"}
    )

    message = classify_llm_error(exc)

    assert "rate-limiting" in message.lower() or "rate limit" in message.lower()
    assert "quota" not in message.lower()


def test_api_connection_error_mentions_network():
    exc = openai.APIConnectionError(request=_REQUEST)

    message = classify_llm_error(exc)

    assert "network" in message.lower() or "reach" in message.lower()


def test_internal_server_error_suggests_retrying():
    exc = _status_error(openai.InternalServerError, 500, {"code": None, "type": "server_error"})

    message = classify_llm_error(exc)

    assert "try again" in message.lower()


def test_ollama_connection_error_mentions_the_ollama_service():
    exc = httpx.ConnectError("Connection refused")

    message = classify_llm_error(exc)

    assert "ollama" in message.lower()


def test_ollama_read_timeout_is_distinguished_from_connection_error():
    exc = httpx.ReadTimeout("timed out")

    message = classify_llm_error(exc)

    assert "ollama" in message.lower()
    assert "loading" in message.lower() or "generating" in message.lower()


def test_qdrant_response_handling_exception_mentions_qdrant():
    exc = ResponseHandlingException(ConnectionError("refused"))

    message = classify_llm_error(exc)

    assert "qdrant" in message.lower()


def test_unrecognized_exception_falls_back_to_the_generic_message():
    message = classify_llm_error(ValueError("something else entirely"))

    assert message == GENERIC_MESSAGE


def test_no_classified_message_leaks_the_original_exception_text():
    # The whole point of this module: known failure categories get a
    # specific, actionable message, but never by way of interpolating the
    # raw exception text into it (that's exactly the leak Phase 7's
    # original generic-message design was there to prevent).
    secret_detail = "db_password=hunter2 at 10.0.0.5"
    exc = ValueError(secret_detail)

    message = classify_llm_error(exc)

    assert secret_detail not in message
