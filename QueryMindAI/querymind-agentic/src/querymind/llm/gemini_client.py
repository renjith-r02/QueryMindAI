"""Shared Gemini client creation and retry handling."""

from __future__ import annotations

import os
import re
import time
from collections.abc import Callable

from querymind.exceptions import MissingApiKeyError

_RETRY_STATUS = {429, 500, 503}
#: Per-request limit. Without one, a stalled response blocks the caller forever; timeouts are retried.
REQUEST_TIMEOUT_SECONDS = 120


def make_client(api_key: str | None = None):
    from google import genai

    api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise MissingApiKeyError(
            "No Gemini API key. Set GEMINI_API_KEY in the environment or in querymind-agentic/.env, "
            "or pass --api-key. Create a key at https://aistudio.google.com/apikey"
        )
    from google.genai import types

    return genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_SECONDS * 1000))


def with_retry[T](call: Callable[[], T], max_retries: int = 5) -> T:
    """Run `call`, retrying rate-limit and transient server errors, and timed-out requests.

    Waits for the server's RetryInfo delay when given (free-tier quotas are per
    minute), otherwise backs off exponentially.
    """
    import httpx
    from google.genai import errors

    for attempt in range(max_retries + 1):
        try:
            return call()
        except httpx.TimeoutException:
            if attempt == max_retries:
                raise
            time.sleep(min(2**attempt, 30))
        except errors.APIError as error:
            if error.code not in _RETRY_STATUS or attempt == max_retries:
                raise
            delay = _server_retry_delay(error)
            time.sleep(min(delay + 1, 90) if delay is not None else min(2**attempt, 30))
    raise AssertionError("unreachable")


def _server_retry_delay(error) -> float | None:
    details = (getattr(error, "details", None) or {}).get("error", {}).get("details", [])
    for detail in details if isinstance(details, list) else []:
        if detail.get("@type", "").endswith("RetryInfo") and (
            match := re.fullmatch(r"([\d.]+)s", str(detail.get("retryDelay", "")))
        ):
            return float(match.group(1))
    return None
