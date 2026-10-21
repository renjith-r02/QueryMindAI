"""Build data sources from the documentation header of the annotated schema files (sqls/)."""

from __future__ import annotations

import re
import textwrap
from pathlib import Path

from querymind.datasources.models import DataSourceInput

_SEPARATOR = re.compile(r"^\s*[-=]{5,}\s*$")
_TITLE = re.compile(r"\(\s*(MySQL|PostgreSQL)[^)]*\).*?database:\s*([\w.]+)", re.I)

# Heading prefix -> section key. The two schema files word some headings differently.
_HEADINGS: list[tuple[str, str]] = [
    ("PURPOSE", "purpose"),
    ("DATA LOCATION MAP", "data_location_map"),
    ("TABLE OVERVIEW", "table_overview"),
    ("RELATIONSHIPS", "relationships"),
    ("ENTITY DIAGRAM", "entity_diagram"),
    ("STANDARD JOIN PATHS", "join_paths"),
    ("QUESTIONS THAT INVOLVE", "returns_questions"),
    ("HOW TO ANSWER QUESTIONS", "returns_questions"),
    ("BUSINESS RULES", "business_rules"),
]


def from_schema_file(path: Path) -> DataSourceInput | None:
    """A data source documented by the file's header, or None if it has no recognisable header."""
    text = path.read_text(encoding="utf-8")
    header_lines = []
    for line in text.splitlines():
        if line.strip() and not line.lstrip().startswith("--"):
            break  # the header ends at the first SQL statement
        header_lines.append(re.sub(r"^\s*--( |$)", "", line))

    title = _TITLE.search("\n".join(header_lines[:4]))
    if not title:
        return None
    dialect, database = title.group(1).lower(), title.group(2)

    # Headings sit between separator lines (----- HEADING -----); PURPOSE follows the title
    # banner without a closing line. The documentation ends at the next ===== banner.
    sections: dict[str, list[str]] = {}
    current: str | None = None
    previous_was_separator = closing_expected = False
    for line in header_lines[2:]:  # skip the title banner
        if _SEPARATOR.match(line):
            if sections and set(line.strip()) == {"="}:
                break
            if closing_expected:  # the line under a heading, not the start of a new one
                closing_expected = False
            else:
                previous_was_separator = True
            continue
        if previous_was_separator and line.strip():
            heading = line.strip()
            current = next((k for prefix, k in _HEADINGS if heading.startswith(prefix)), None)
            if current is not None:
                sections.setdefault(current, [])
            previous_was_separator, closing_expected = False, True
            continue
        previous_was_separator = closing_expected = False
        if current is not None:
            sections[current].append(line)

    port = "3306" if dialect == "mysql" else "5432"
    connection = {"host": "localhost", "port": port, "database": database}
    return DataSourceInput(
        name=database,
        type=dialect,  # type: ignore[arg-type]
        connection=connection,
        sections={key: _clean(lines) for key, lines in sections.items() if _clean(lines)},  # type: ignore[misc]
    )


def _clean(lines: list[str]) -> str:
    text = textwrap.dedent("\n".join(lines)).strip("\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return "\n".join(re.sub(r"^ {1,2}", "", line) for line in text.splitlines()).rstrip()
