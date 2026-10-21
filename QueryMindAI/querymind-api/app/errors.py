"""Map errors from the shared QueryMind service to HTTP status codes and safe messages.

Used by the exception handlers (normal responses) and by the event streams, which
cannot change their status code once streaming has started.
"""

import logging

import openai
from fastapi import status
from google.genai import errors as genai_errors
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse
from querymind.exceptions import (
    CollectionMismatchError,
    MissingApiKeyError,
    NoSourceFilesError,
)

logger = logging.getLogger("querymind.api")

HANDLED = (
    MissingApiKeyError,
    CollectionMismatchError,
    NoSourceFilesError,
    ResponseHandlingException,
    UnexpectedResponse,
    genai_errors.APIError,
    openai.APIError,
)


def describe_error(error: Exception) -> tuple[int, str]:
    """HTTP status and client-safe message for an error raised by the service."""
    if isinstance(error, MissingApiKeyError):
        logger.error("%s", error)
        return (
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "The model provider's API key is not configured on the server.",
        )
    if isinstance(error, CollectionMismatchError):
        return status.HTTP_409_CONFLICT, f"{error} Use POST /index with recreate=true."
    if isinstance(error, NoSourceFilesError):
        return (
            status.HTTP_404_NOT_FOUND,
            "No .sql or .json source files are available to index.",
        )
    if isinstance(error, (ResponseHandlingException, UnexpectedResponse)):
        logger.exception("Qdrant request failed", exc_info=error)
        return status.HTTP_503_SERVICE_UNAVAILABLE, "The vector store is unavailable."
    if isinstance(error, genai_errors.APIError):
        logger.exception("Gemini request failed", exc_info=error)
        return (
            status.HTTP_502_BAD_GATEWAY,
            f"The language model request failed ({error.code}).",
        )
    if isinstance(error, openai.APIError):
        logger.exception("OpenAI request failed", exc_info=error)
        code = getattr(error, "status_code", None) or type(error).__name__
        return (
            status.HTTP_502_BAD_GATEWAY,
            f"The language model request failed ({code}).",
        )
    logger.exception("Unexpected error", exc_info=error)
    return status.HTTP_500_INTERNAL_SERVER_ERROR, "Internal server error."
