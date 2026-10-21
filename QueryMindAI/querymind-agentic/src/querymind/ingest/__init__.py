"""Turn annotated schema files and question/SQL pairs into knowledge chunks."""

from querymind.ingest.models import Chunk
from querymind.ingest.qa_loader import load_qa_file
from querymind.ingest.sql_parser import parse_sql, parse_sql_file

__all__ = ["Chunk", "load_qa_file", "parse_sql", "parse_sql_file"]
