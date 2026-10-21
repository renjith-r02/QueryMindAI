"""Run generated SQL read-only against the configured databases."""

from querymind.database.executor import DatabaseRegistry, QueryResult, merge_results
from querymind.database.safety import check_read_only, check_update, ensure_read_only

__all__ = ["DatabaseRegistry", "QueryResult", "check_read_only", "check_update", "ensure_read_only", "merge_results"]
