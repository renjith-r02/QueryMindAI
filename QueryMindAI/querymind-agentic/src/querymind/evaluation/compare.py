"""The two text-to-SQL metrics.

Execution accuracy: run the generated and the ground-truth SQL and compare the result sets
row by row. Column names are ignored (aliases differ); columns may come in another order;
rows are compared as a multiset unless the test case says order matters. Numbers compare
as numbers (5 == 5.00). Non-integral numbers match within 0.5%, or when the more precise
one rounds to the other (8.6477 == 8.6), so rounding doesn't count as a wrong answer.
The relaxed variant also accepts extra columns.

Exact match: both statements normalised by sqlglot (whitespace, keyword and identifier case,
quoting) and compared as text. Semantic match: exact match, or sqlglot.diff() finds no edits
between the two syntax trees after table aliases and output-column aliases are normalised,
columns are qualified from the database schema, and (when row order doesn't matter) a final
ORDER BY without LIMIT is dropped.
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import permutations
from typing import Any

import sqlglot
from sqlglot import exp
from sqlglot.diff import Keep
from sqlglot.optimizer.qualify import qualify

from querymind.database.executor import QueryResult

_REL_TOL = 0.005
_MAX_PERMUTED_COLUMNS = 7  # beyond this, columns are matched greedily


# -- execution accuracy ---------------------------------------------------------------------


@dataclass
class ResultComparison:
    match: bool  # same rows, same number of columns (any column order)
    relaxed_match: bool  # same rows on the ground-truth columns; extra columns allowed
    reason: str = ""


def normalise(value: Any) -> Any:
    """A comparable form of one cell: numbers as float, booleans as 0/1, text without padding."""
    if value is None:
        return None
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        return value.rstrip()
    return str(value)


def _decimals(value: float) -> int | None:
    text = repr(value)
    return len(text.split(".")[1]) if "." in text and "e" not in text else None


def values_equal(a: Any, b: Any) -> bool:
    if isinstance(a, float) and isinstance(b, float):
        if a.is_integer() and b.is_integer():
            return a == b
        if math.isclose(a, b, rel_tol=_REL_TOL, abs_tol=_REL_TOL):
            return True
        # One side rounded: compare at the coarser precision (at least one decimal place).
        places = [d for d in (_decimals(a), _decimals(b)) if d is not None]
        return bool(places) and (d := min(places)) >= 1 and round(a, d) == round(b, d)
    return a == b


def _sort_key(row: Sequence[Any]) -> tuple:
    # Type-tagged so None, numbers and text sort together without errors; numbers rounded so
    # near-equal values land in the same position.
    return tuple(
        (0, 0.0, "") if v is None else (1, round(v, 2), "") if isinstance(v, float) else (2, 0.0, str(v)) for v in row
    )


def _rows_equal(expected: list[tuple], actual: list[tuple], ordered: bool) -> bool:
    if len(expected) != len(actual):
        return False
    if not ordered:
        expected, actual = sorted(expected, key=_sort_key), sorted(actual, key=_sort_key)
    return all(
        len(e) == len(a) and all(values_equal(x, y) for x, y in zip(e, a, strict=True))
        for e, a in zip(expected, actual, strict=True)
    )


def _column(rows: list[tuple], index: int) -> list[tuple]:
    return [(row[index],) for row in rows]


def _column_mappings(expected: list[tuple], actual: list[tuple], width: int, actual_width: int):
    """Candidate mappings of ground-truth columns to generated columns whose values agree."""
    candidates = [
        [k for k in range(actual_width) if _rows_equal(_column(expected, j), _column(actual, k), ordered=False)]
        for j in range(width)
    ]
    if any(not options for options in candidates):
        return
    if actual_width <= _MAX_PERMUTED_COLUMNS:
        for chosen in permutations(range(actual_width), width):
            if all(chosen[j] in candidates[j] for j in range(width)):
                yield chosen
    else:  # greedy: first unused candidate per column
        used: set[int] = set()
        chosen = []
        for options in candidates:
            pick = next((k for k in options if k not in used), None)
            if pick is None:
                return
            used.add(pick)
            chosen.append(pick)
        yield tuple(chosen)


def compare_results(expected: QueryResult, actual: QueryResult, order_matters: bool = False) -> ResultComparison:
    """Compare a generated result table with the ground-truth one."""
    if not expected.ok:
        return ResultComparison(False, False, f"ground truth failed: {expected.error}")
    if not actual.ok:
        return ResultComparison(False, False, f"generated SQL failed: {actual.error}")
    gt = [tuple(normalise(v) for v in row) for row in expected.rows]
    gen = [tuple(normalise(v) for v in row) for row in actual.rows]
    width, actual_width = len(expected.columns), len(actual.columns)
    if len(gt) != len(gen):
        return ResultComparison(False, False, f"{len(gen)} rows instead of {len(gt)}")
    if actual_width < width:
        return ResultComparison(False, False, f"{actual_width} columns instead of {width}")

    for mapping in _column_mappings(gt, gen, width, actual_width):
        projected = [tuple(row[k] for k in mapping) for row in gen]
        if _rows_equal(gt, projected, order_matters):
            if actual_width == width:
                return ResultComparison(True, True)
            return ResultComparison(False, True, f"{actual_width - width} extra column(s)")
    if order_matters and any(True for _ in _column_mappings(gt, gen, width, actual_width)):
        return ResultComparison(False, False, "same rows in a different order")
    return ResultComparison(False, False, "different values")


# -- exact and semantic match ---------------------------------------------------------------


def _read_dialect(dialect: str) -> str:
    return "postgres" if dialect in {"postgresql", "postgres"} else dialect


def normalise_sql(sql: str, dialect: str) -> str:
    """Whitespace, keyword case, identifier case and quoting normalised; trailing ';' removed."""
    sql = sql.strip().rstrip(";").strip()
    try:
        tree = sqlglot.parse_one(sql, read=_read_dialect(dialect))
        return tree.sql(dialect=_read_dialect(dialect), normalize=True, normalize_functions="upper")
    except sqlglot.errors.ParseError:
        return re.sub(r"\s+", " ", sql).lower()


def exact_match(generated: str, ground_truth: str, dialect: str) -> bool:
    return normalise_sql(generated, dialect) == normalise_sql(ground_truth, dialect)


def _canonical_tree(sql: str, dialect: str, schema: dict | None, ignore_order: bool = False) -> exp.Expression:
    read = _read_dialect(dialect)
    tree = sqlglot.parse_one(sql.strip().rstrip(";"), read=read)
    if schema:
        try:
            tree = qualify(tree, schema=schema, dialect=read, validate_qualify_columns=False, quote_identifiers=False)
        except Exception:  # noqa: BLE001 - qualification is best effort
            tree = sqlglot.parse_one(sql.strip().rstrip(";"), read=read)

    # Table aliases -> table names (when the table appears once), so `orders o` == `orders`.
    tables = list(tree.find_all(exp.Table))
    names = [table.name.lower() for table in tables]
    aliases = {
        table.alias.lower(): table.name.lower()
        for table in tables
        if table.alias and names.count(table.name.lower()) == 1
    }
    for table in tables:
        if table.alias and table.alias.lower() in aliases:
            table.set("alias", None)
    for column in tree.find_all(exp.Column):
        if column.table and column.table.lower() in aliases:
            column.set("table", exp.to_identifier(aliases[column.table.lower()]))

    # Output-column aliases don't change the values returned; nor does the final ORDER BY when the
    # question asks for no order (unless a LIMIT depends on it).
    if isinstance(tree, exp.Select):
        tree.set("expressions", [e.this if isinstance(e, exp.Alias) else e for e in tree.expressions])
        if ignore_order and not tree.args.get("limit"):
            tree.set("order", None)
    return exp.maybe_parse(tree.sql(dialect=read, normalize=True), dialect=read)


def semantic_match(
    generated: str, ground_truth: str, dialect: str, schema: dict | None = None, ignore_order: bool = False
) -> tuple[bool, int]:
    """(equivalent, number of edits) by sqlglot.diff over normalised syntax trees.

    `ignore_order`: the question asks for no particular order, so a top-level ORDER BY
    (without LIMIT) on either side is not a difference."""
    if exact_match(generated, ground_truth, dialect):
        return True, 0
    try:
        source = _canonical_tree(ground_truth, dialect, schema, ignore_order)
        target = _canonical_tree(generated, dialect, schema, ignore_order)
    except sqlglot.errors.ParseError:
        return False, -1
    edits = [edit for edit in sqlglot.diff(source, target) if not isinstance(edit, Keep)]
    return not edits, len(edits)
