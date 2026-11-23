"""Provider-agnostic retry wrapper for LangGraph agent invocations.

Both Groq and Anthropic enforce rate limits and may return 429 or overload
responses mid-run. This module detects rate-limit signals in any exception
message and retries with an appropriate back-off, reading the Retry-After
header when the response object carries one.
"""

import time

DEFAULT_WAIT_SECONDS = 15.0
WAIT_BUFFER_SECONDS = 3.0

# Phrases that appear in rate-limit and overload errors across LLM providers.
_RATE_LIMIT_SIGNALS = (
    "rate limit", "rate_limit", "429", "too many requests", "overloaded",
    "capacity", "quota exceeded",
)


def _is_rate_limit_error(exc: Exception) -> bool:
    """Return True when the exception looks like an API rate-limit or overload."""
    msg = str(exc).lower()
    return any(sig in msg for sig in _RATE_LIMIT_SIGNALS)


def _read_retry_after(exc: Exception) -> float | None:
    """Try to read a Retry-After header from the exception's response object.

    Both httpx and requests attach a 'response' attribute to HTTP exceptions.
    Returns the header value plus a small buffer, or None when unavailable.
    """
    try:
        response = getattr(exc, "response", None) or getattr(exc, "http_response", None)
        if response is None:
            return None
        headers = getattr(response, "headers", {}) or {}
        value = headers.get("retry-after") or headers.get("Retry-After")
        if value:
            return float(value) + WAIT_BUFFER_SECONDS
    except Exception:
        pass
    return None


def invoke_with_retry(agent, messages: dict, max_retries: int = 6):
    """Call agent.invoke(messages), retrying on rate-limit errors from any LLM provider.

    Non-rate-limit exceptions are re-raised immediately so the caller sees the
    real error rather than waiting through several pointless retry cycles.
    """
    for attempt in range(max_retries):
        try:
            return agent.invoke(messages)
        except Exception as e:
            if not _is_rate_limit_error(e):
                raise
            if attempt == max_retries - 1:
                raise
            wait_s = _read_retry_after(e) or DEFAULT_WAIT_SECONDS
            print(
                f"[LLM] Rate limited — waiting {wait_s:.1f}s "
                f"before retry {attempt + 1}/{max_retries - 1}"
            )
            time.sleep(wait_s)
