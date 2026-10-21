"""QueryMind: answer questions about your databases in plain English.

Index database knowledge (schema DDL, documentation, business rules and question -> SQL
examples) into a vector store, generate read-only SQL with an LLM, run it, and answer
from the results.

Subpackages:
    ingest      parse annotated schema files and question/SQL pairs into chunks
    knowledge   embeddings and the Qdrant knowledge store
    llm         language model providers (Gemini, OpenAI)
    database    read-only query execution and SQL safety checks
    agent       retrieval-augmented SQL generation and the run/repair/answer loop

Entry points: `querymind.service.QueryMindService` (used by the CLI and the HTTP API)
and the `querymind` command (`querymind.cli`).
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("querymindai")
except PackageNotFoundError:  # running from a source tree without installing
    __version__ = "0.0.0"

__all__ = ["__version__"]
