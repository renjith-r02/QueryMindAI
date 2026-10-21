"""Errors raised by QueryMind. All derive from QueryMindError.

Each also keeps its original built-in base (RuntimeError / ValueError), so callers that
caught those before keep working.
"""


class QueryMindError(Exception):
    """Base class for QueryMind errors."""


class MissingApiKeyError(QueryMindError, RuntimeError):
    """The model provider's API key is not configured."""


class CollectionMismatchError(QueryMindError, RuntimeError):
    """The vector collection was built with a different embedding size."""


class NoSourceFilesError(QueryMindError, RuntimeError):
    """There are no .sql or .json files to index."""


class UnsafeQueryError(QueryMindError, ValueError):
    """Generated SQL is not a single read-only statement."""
