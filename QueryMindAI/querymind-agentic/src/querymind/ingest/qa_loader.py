"""Load curated question -> SQL pairs from a JSON file.

Expected format (a list, or an object with a "pairs" list):

    [
      {
        "question": "How many orders were placed last week?",
        "sql": "SELECT COUNT(*) FROM orders WHERE placed_at >= NOW() - INTERVAL 7 DAY;",
        "database": "ecommerce",
        "dialect": "mysql",
        "notes": "optional explanation",
        "id": "optional id, e.g. FS01",
        "query_type": "optional label, e.g. SELECT_TEMPORAL"
      }
    ]

"answer" may be given instead of (or in addition to) "sql" for multi-step answers.
"""

from __future__ import annotations

import json
from pathlib import Path

from querymind.ingest.models import Chunk


def load_qa_file(path: str | Path) -> list[Chunk]:
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    pairs = data["pairs"] if isinstance(data, dict) else data

    chunks = []
    for index, pair in enumerate(pairs, start=1):
        question = (pair.get("question") or "").strip()
        sql = (pair.get("sql") or "").strip() or None
        answer = (pair.get("answer") or "").strip() or sql
        if not question or not answer:
            raise ValueError(f"{path.name}: pair #{index} needs a 'question' and a 'sql' or 'answer'")
        database = pair.get("database", "unknown")
        dialect = pair.get("dialect", "unknown").lower()
        notes = (pair.get("notes") or "").strip() or None

        content = f"Question: {question}\nDatabase: {database} ({dialect})\nAnswer:\n{answer}"
        if notes:
            content += f"\nNotes: {notes}"
        metadata = {
            "question": question,
            "answer": answer,
            "sql": sql,
            "notes": notes,
            "example_id": pair.get("id"),
            "query_type": pair.get("query_type"),
        }
        chunks.append(
            Chunk(
                doc_type="qa_pair",
                title=question[:80],
                embed_text=question,
                content=content,
                database=database,
                dialect=dialect,
                source=path.name,
                metadata={k: v for k, v in metadata.items() if v},
            )
        )
    return chunks
