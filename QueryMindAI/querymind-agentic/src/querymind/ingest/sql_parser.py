"""Parse an annotated SQL schema file into knowledge chunks.

The parser understands the conventions used in the files under ``sqls/``:

* ``--`` comment blocks wrapped in banner lines (``-- ====`` / ``-- ----``)
  hold documentation sections (overview, relationships, join paths, ...).
* A "BUSINESS RULES" section holds numbered rules (``1. ...``).
* An "EXAMPLE QUESTIONS" section holds ``Qn: question`` followed by SQL.
* MySQL column/table documentation is inline (``COMMENT '...'``);
  PostgreSQL documentation is in ``COMMENT ON TABLE/COLUMN/VIEW`` statements.
* A short comment block right before a statement annotates that statement.
"""

from __future__ import annotations

import re
import textwrap
from dataclasses import dataclass, field
from pathlib import Path

from querymind.ingest.models import Chunk

# A comment block with more lines than this (and not followed directly by a
# statement) is treated as documentation rather than an annotation.
_ANNOTATION_MAX_LINES = 12

_SEPARATOR = re.compile(r"\s*[-=]{5,}\s*")
_GROUP_HEADING = re.compile(r"-{2,}\s*(.+?)\s*-{2,}")
_QUESTION = re.compile(r"Q(\d+)\s*[:.)]\s*(.*)")
_RULE = re.compile(r"\s{0,4}(\d{1,2})\.\s+(.*)")
_SQL_START = re.compile(r"(SELECT|WITH)\b", re.I)

_NAME = r"([\w.`\"]+)"
_STRING = r"'((?:[^']|'')*)'"
_CREATE_TABLE = re.compile(rf"CREATE\s+(?:TEMPORARY\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?{_NAME}\s*\(", re.I)
_CREATE_VIEW = re.compile(rf"CREATE\s+(?:OR\s+REPLACE\s+)?(?:MATERIALIZED\s+)?VIEW\s+{_NAME}", re.I)
_CREATE_INDEX = re.compile(
    rf"CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:CONCURRENTLY\s+)?(?:IF\s+NOT\s+EXISTS\s+)?\S+\s+ON\s+{_NAME}",
    re.I,
)
_CREATE_TRIGGER = re.compile(rf"CREATE\s+(?:OR\s+REPLACE\s+)?TRIGGER\s+\S+.*?\bON\s+{_NAME}", re.I | re.S)
_CREATE_ROUTINE = re.compile(rf"CREATE\s+(?:OR\s+REPLACE\s+)?(?:FUNCTION|PROCEDURE)\s+{_NAME}", re.I)
_COMMENT_ON = re.compile(
    rf"COMMENT\s+ON\s+(TABLE|COLUMN|VIEW|MATERIALIZED\s+VIEW|SCHEMA)\s+{_NAME}\s+IS\s+{_STRING}",
    re.I | re.S,
)
_INLINE_COMMENT = re.compile(rf"\s*COMMENT\s*=?\s*{_STRING}", re.I | re.S)
_CONSTRAINT = re.compile(
    r"(CONSTRAINT|PRIMARY\s+KEY|UNIQUE|KEY|INDEX|FOREIGN\s+KEY|CHECK|FULLTEXT|SPATIAL|EXCLUDE)\b",
    re.I,
)
_FOREIGN_KEY = re.compile(rf"FOREIGN\s+KEY\s*\(([^)]*)\)\s*REFERENCES\s+{_NAME}\s*\(([^)]*)\)", re.I)


@dataclass
class _Column:
    name: str
    definition: str
    comment: str = ""


@dataclass
class _Relation:
    name: str
    kind: str  # "table" | "view"
    ddl: str
    annotation: str = ""
    comment: str = ""
    columns: list[_Column] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    indexes: list[str] = field(default_factory=list)
    triggers: list[str] = field(default_factory=list)


@dataclass
class _Context:
    database: str
    dialect: str
    source: str

    @property
    def label(self) -> str:
        return f"{self.database} ({_DIALECT_LABELS.get(self.dialect, self.dialect)})"

    def chunk(self, doc_type: str, title: str, content: str, embed_text: str | None = None, **metadata) -> Chunk:
        return Chunk(
            doc_type=doc_type,
            title=title,
            embed_text=embed_text or content,
            content=content,
            database=self.database,
            dialect=self.dialect,
            source=self.source,
            metadata={k: v for k, v in metadata.items() if v not in (None, "", [])},
        )


_DIALECT_LABELS = {"mysql": "MySQL", "postgresql": "PostgreSQL"}


def parse_sql_file(path: str | Path, database: str | None = None, dialect: str | None = None) -> list[Chunk]:
    path = Path(path)
    return parse_sql(path.read_text(encoding="utf-8"), source=path.name, database=database, dialect=dialect)


def parse_sql(text: str, source: str, database: str | None = None, dialect: str | None = None) -> list[Chunk]:
    segments = _split_segments(text)
    doc_blocks, statements = _classify_segments(segments)

    header = "\n".join(line for block in doc_blocks[:1] for line in block)
    ctx = _Context(
        database=database or _detect_database(header, statements, source),
        dialect=dialect or _detect_dialect(header, source),
        source=source,
    )

    chunks: list[Chunk] = []
    for index, block in enumerate(doc_blocks):
        chunks.extend(_doc_block_chunks(block, ctx, is_header=index == 0))
    chunks.extend(_statement_chunks(statements, ctx))
    return chunks


# ---------------------------------------------------------------------------
# Lexing: split the file into comment blocks and SQL statements
# ---------------------------------------------------------------------------


def _uncomment(line: str) -> str:
    return re.sub(r"^\s*--\s?", "", line).rstrip()


def _scan_line(line: str, state: str | None) -> tuple[str | None, bool]:
    """Advance the quote state over one line; report whether a top-level ';' was seen."""
    ended = False
    i = 0
    while i < len(line):
        if state is None:
            if line.startswith("--", i):
                break
            char = line[i]
            if char == "'":
                state = "'"
            elif char == "$" and (tag := re.match(r"\$\w*\$", line[i:])):
                state = tag.group()
                i += len(state)
                continue
            elif char == ";":
                ended = True
        elif state == "'":
            if line.startswith("''", i):
                i += 2
                continue
            if line[i] == "'":
                state = None
        elif line.startswith(state, i):
            i += len(state)
            state = None
            continue
        i += 1
    return state, ended and state is None


def _split_segments(text: str) -> list[tuple[str, list[str] | str]]:
    """Return ("comment", lines) and ("stmt", sql) segments in file order.

    Comment blocks are runs of consecutive comment lines; a blank line ends a block.
    """
    segments: list[tuple[str, list[str] | str]] = []
    comment_run: list[str] = []
    statement: list[str] = []
    state: str | None = None

    def flush_comments() -> None:
        if comment_run:
            segments.append(("comment", comment_run.copy()))
            comment_run.clear()

    for line in text.splitlines():
        stripped = line.strip()
        if not statement:
            if stripped.startswith("--"):
                comment_run.append(_uncomment(line))
                continue
            flush_comments()
            if not stripped:
                continue
        statement.append(line)
        state, ended = _scan_line(line, state)
        if ended:
            segments.append(("stmt", "\n".join(statement).strip()))
            statement = []

    flush_comments()
    if statement:
        segments.append(("stmt", "\n".join(statement).strip()))
    return segments


def _content_lines(lines: list[str]) -> list[str]:
    return [line for line in lines if line.strip() and not _SEPARATOR.fullmatch(line)]


def _classify_segments(segments) -> tuple[list[list[str]], list[tuple[str, str]]]:
    """Split comment blocks into documentation blocks and statement annotations."""
    doc_blocks: list[list[str]] = []
    statements: list[tuple[str, str]] = []  # (sql, annotation)
    for i, (kind, value) in enumerate(segments):
        if kind == "stmt":
            previous = segments[i - 1] if i else None
            annotation = ""
            if previous and previous[0] == "comment" and len(_content_lines(previous[1])) <= _ANNOTATION_MAX_LINES:
                annotation = _annotation_text(previous[1])
            statements.append((value, annotation))
            continue
        follows_statement = i + 1 < len(segments) and segments[i + 1][0] == "stmt"
        if _content_lines(value) and (not follows_statement or len(_content_lines(value)) > _ANNOTATION_MAX_LINES):
            doc_blocks.append(value)
    return doc_blocks, statements


def _annotation_text(lines: list[str]) -> str:
    # Drop all-caps banner titles such as "USERS" or "RMA.RETURNS".
    kept = [line.strip() for line in _content_lines(lines) if line.strip() != line.strip().upper()]
    return " ".join(kept)


# ---------------------------------------------------------------------------
# Documentation blocks
# ---------------------------------------------------------------------------


def _sections(lines: list[str]) -> list[tuple[str, list[str]]]:
    """Split a comment block into (title, body_lines) using banner separators."""
    parts: list[list[str]] = [[]]
    for line in lines:
        if _SEPARATOR.fullmatch(line):
            parts.append([])
        else:
            parts[-1].append(line)

    sections: list[tuple[str, list[str]]] = []
    if _content_lines(parts[0]):
        sections.append(("", parts[0]))
    rest = parts[1:]
    i = 0
    while i < len(rest):
        text = _content_lines(rest[i])
        if not text:
            i += 1
            continue
        if len(text) <= 3 and i + 1 < len(rest):
            sections.append((" ".join(" ".join(t.split()) for t in text), rest[i + 1]))
            i += 2
        else:
            sections.append(("", rest[i]))
            i += 1
    return sections


def _body_text(lines: list[str]) -> str:
    return textwrap.dedent("\n".join(lines)).strip("\n")


def _doc_block_chunks(lines: list[str], ctx: _Context, is_header: bool) -> list[Chunk]:
    chunks: list[Chunk] = []
    for index, (title, body) in enumerate(_sections(lines)):
        if not _content_lines(body):
            continue
        upper = title.upper()
        if "BUSINESS RULES" in upper:
            chunks.extend(_rule_chunks(title, body, ctx))
        elif "EXAMPLE QUESTIONS" in upper:
            chunks.extend(_example_chunks(body, ctx))
        else:
            is_overview = is_header and index == 0
            doc_type = "overview" if is_overview else "section"
            title = title or ("Overview" if is_overview else "Notes")
            content = f"{title}\nDatabase: {ctx.label}\n\n{_body_text(body)}"
            chunks.append(ctx.chunk(doc_type, title, content, section=title))
    return chunks


def _rule_chunks(section: str, body: list[str], ctx: _Context) -> list[Chunk]:
    rules: list[tuple[int, list[str]]] = []
    for line in body:
        if match := _RULE.match(line):
            rules.append((int(match.group(1)), [match.group(2)]))
        elif rules and line.strip():
            rules[-1][1].append(line)

    chunks = []
    for number, lines in rules:
        # Keep the layout of continuation lines: rules often contain formulas.
        text = "\n".join([lines[0], *textwrap.indent(textwrap.dedent("\n".join(lines[1:])), "  ").splitlines()])
        title = f"Rule {number}: {lines[0][:80]}"
        content = f"Business rule {number} for {ctx.label}:\n{text}"
        chunks.append(ctx.chunk("business_rule", title, content, section=section, rule_number=number))
    return chunks


def _example_chunks(body: list[str], ctx: _Context) -> list[Chunk]:
    examples: list[dict] = []
    group = ""
    for line in body:
        stripped = line.strip()
        if not stripped:
            continue
        if heading := _GROUP_HEADING.fullmatch(stripped):
            group = heading.group(1)
            continue
        if question := _QUESTION.match(stripped):
            examples.append(
                {"number": int(question.group(1)), "question": [question.group(2)], "answer": [], "group": group}
            )
            continue
        if not examples:
            continue
        current = examples[-1]
        indent = len(line) - len(line.lstrip())
        if not current["answer"] and indent >= 4:
            current["question"].append(stripped)  # wrapped question line
        else:
            current["answer"].append(line)

    chunks = []
    for example in examples:
        question = " ".join(example["question"])
        answer = textwrap.dedent("\n".join(example["answer"])).strip()
        sql, notes = _split_sql_and_notes(answer)
        content = f"Question: {question}\nDatabase: {ctx.label}\n"
        if example["group"]:
            content += f"Scope: {example['group']}\n"
        content += f"Answer:\n{answer}"
        chunks.append(
            ctx.chunk(
                "example_query",
                f"Q{example['number']}: {question[:80]}",
                content,
                embed_text=question,
                question=question,
                answer=answer,
                sql=sql,
                notes=notes,
                scope=example["group"],
            )
        )
    return chunks


def _split_sql_and_notes(answer: str) -> tuple[str | None, str | None]:
    """Return (sql, notes) when the answer is a single SQL query, else (None, None)."""
    if not _SQL_START.match(answer):
        return None, None
    lines = answer.splitlines()
    for i, line in enumerate(lines[1:], start=1):
        # A parenthesised note or a prose label such as "Merge:" ends the SQL.
        if line.startswith("(") or re.match(r"[A-Z][a-z]+( [a-z]+)*:", line):
            return "\n".join(lines[:i]).strip(), "\n".join(lines[i:]).strip()
    return answer, None


# ---------------------------------------------------------------------------
# Statements
# ---------------------------------------------------------------------------


def _clean_name(name: str) -> str:
    return name.replace("`", "").replace('"', "").lower()


def _unquote(value: str) -> str:
    return " ".join(value.replace("''", "'").split())


def _matching_paren(text: str, start: int) -> int:
    depth, quoted = 0, False
    for i in range(start, len(text)):
        char = text[i]
        if char == "'":
            quoted = not quoted
        elif not quoted and char == "(":
            depth += 1
        elif not quoted and char == ")":
            depth -= 1
            if depth == 0:
                return i
    return len(text)


def _split_top_level(text: str) -> list[str]:
    items, current, depth, quoted = [], [], 0, False
    for char in text:
        if char == "'":
            quoted = not quoted
        elif not quoted and char == "(":
            depth += 1
        elif not quoted and char == ")":
            depth -= 1
        elif not quoted and depth == 0 and char == ",":
            items.append("".join(current))
            current = []
            continue
        current.append(char)
    items.append("".join(current))
    return [" ".join(item.split()) for item in items if item.strip()]


def _parse_table(sql: str, match: re.Match, annotation: str) -> _Relation:
    open_paren = match.end() - 1
    close_paren = _matching_paren(sql, open_paren)
    relation = _Relation(_clean_name(match.group(1)), "table", sql, annotation)

    for item in _split_top_level(sql[open_paren + 1 : close_paren]):
        if _CONSTRAINT.match(item):
            relation.constraints.append(item)
            continue
        comment = _INLINE_COMMENT.search(item)
        definition = _INLINE_COMMENT.sub("", item).strip()
        name, _, definition = definition.partition(" ")
        relation.columns.append(_Column(_clean_name(name), definition, _unquote(comment.group(1)) if comment else ""))

    if table_comment := _INLINE_COMMENT.search(sql[close_paren:]):
        relation.comment = _unquote(table_comment.group(1))
    return relation


def _statement_chunks(statements: list[tuple[str, str]], ctx: _Context) -> list[Chunk]:
    relations: dict[str, _Relation] = {}
    column_comments: dict[tuple[str, str], str] = {}
    chunks: list[Chunk] = []

    for sql, annotation in statements:
        if match := _CREATE_TABLE.match(sql):
            relation = _parse_table(sql, match, annotation)
            relations[relation.name] = relation
        elif match := _CREATE_VIEW.match(sql):
            name = _clean_name(match.group(1))
            relations[name] = _Relation(name, "view", sql, annotation)
        elif match := _CREATE_INDEX.match(sql):
            if relation := relations.get(_clean_name(match.group(1))):
                relation.indexes.append(" ".join(sql.split()))
        elif match := _CREATE_TRIGGER.match(sql):
            if relation := relations.get(_clean_name(match.group(1))):
                relation.triggers.append(" ".join(sql.split()))
        elif match := _CREATE_ROUTINE.match(sql):
            name = _clean_name(match.group(1))
            content = f"Routine {name} in {ctx.label}\n{annotation}\n\n{sql}".replace("\n\n\n", "\n\n")
            chunks.append(ctx.chunk("routine", name, content, ddl=sql))
        elif match := _COMMENT_ON.match(sql):
            kind = " ".join(match.group(1).upper().split())
            target, comment = _clean_name(match.group(2)), _unquote(match.group(3))
            if kind == "COLUMN":
                table, _, column = target.rpartition(".")
                column_comments[(table, column)] = comment
            elif kind == "SCHEMA":
                content = f"Schema {target} in {ctx.label}: {comment}"
                chunks.append(ctx.chunk("schema", target, content, schema=target))
            elif relation := relations.get(target):
                relation.comment = comment

    for relation in relations.values():
        for column in relation.columns:
            column.comment = column_comments.get((relation.name, column.name), column.comment)
        chunks.append(_relation_chunk(relation, ctx))
        chunks.extend(_column_chunks(relation, ctx))
    return chunks


def _relation_chunk(relation: _Relation, ctx: _Context) -> Chunk:
    kind = relation.kind.capitalize()
    lines = [f"{kind}: {relation.name}", f"Database: {ctx.label}"]
    if relation.comment:
        lines.append(f"Description: {relation.comment}")
    if relation.annotation:
        lines.append(f"Notes: {relation.annotation}")
    if relation.columns:
        lines.append("Columns:")
        for column in relation.columns:
            entry = f"  - {column.name} {column.definition}"
            lines.append(f"{entry} -- {column.comment}" if column.comment else entry)
    foreign_keys = [
        f"  - ({fk.group(1)}) -> {_clean_name(fk.group(2))}({fk.group(3)})"
        for constraint in relation.constraints
        if (fk := _FOREIGN_KEY.search(constraint))
    ]
    if foreign_keys:
        lines += ["Foreign keys:", *foreign_keys]
    other = [c for c in relation.constraints if not _FOREIGN_KEY.search(c)]
    if other:
        lines += ["Constraints and keys:", *(f"  - {c}" for c in other)]
    if relation.indexes:
        lines += ["Indexes:", *(f"  - {i}" for i in relation.indexes)]
    if relation.triggers:
        lines += ["Triggers:", *(f"  - {t}" for t in relation.triggers)]
    if relation.kind == "view":
        lines += ["Definition:", relation.ddl]

    column_names = ", ".join(c.name for c in relation.columns)
    embed_text = " ".join(
        filter(
            None,
            [
                f"{kind} {relation.name} in {ctx.label}.",
                relation.comment,
                relation.annotation,
                f"Columns: {column_names}." if column_names else "",
                relation.ddl if relation.kind == "view" else "",
            ],
        )
    )
    return ctx.chunk(
        relation.kind,
        relation.name,
        "\n".join(lines),
        embed_text=embed_text,
        table=relation.name,
        columns=[c.name for c in relation.columns],
        ddl=relation.ddl,
    )


def _column_chunks(relation: _Relation, ctx: _Context) -> list[Chunk]:
    chunks = []
    for column in relation.columns:
        qualified = f"{relation.name}.{column.name}"
        content = f"Column {qualified} ({column.definition}) of {relation.kind} {relation.name} in {ctx.label}."
        if column.comment:
            content += f" {column.comment}"
        chunks.append(ctx.chunk("column", qualified, content, table=relation.name, column=column.name))
    return chunks


# ---------------------------------------------------------------------------
# Database / dialect detection
# ---------------------------------------------------------------------------


def _detect_dialect(header: str, source: str) -> str:
    if match := re.search(r"SQL DIALECT:\s*(\w+)", header, re.I):
        candidate = match.group(1).lower()
    else:
        candidate = f"{header[:300]} {source}".lower()
    if "postgres" in candidate:
        return "postgresql"
    if "mysql" in candidate:
        return "mysql"
    return "unknown"


def _detect_database(header: str, statements: list[tuple[str, str]], source: str) -> str:
    if match := re.search(r"database:\s*`?(\w+)", header, re.I):
        return match.group(1)
    for sql, _ in statements:
        if match := re.match(r"CREATE\s+DATABASE\s+(?:IF\s+NOT\s+EXISTS\s+)?`?(\w+)", sql, re.I):
            return match.group(1)
    return Path(source).stem
