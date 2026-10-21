"""Write an evaluation run as Markdown (for people) and JSON (for comparing runs)."""

from __future__ import annotations

import json
from pathlib import Path

from querymind.evaluation.harness import EvaluationRun, summary

_TYPE_LABELS = {
    "SELECT_SIMPLE": "Simple lookup",
    "SELECT_AGGREGATE": "Aggregate",
    "SELECT_JOIN": "Join",
    "SELECT_TEMPORAL": "Temporal",
}
PASSING_EXECUTION_ACCURACY = 0.5


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def _mark(flag: bool) -> str:
    return "✅" if flag else "❌"


def _cell(text: str | None, limit: int = 140) -> str:
    text = " ".join((text or "").split()).replace("|", "\\|")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _rates_row(label: str, rates: dict) -> str:
    return (
        f"| {label} | {rates['cases']} | {_pct(rates['execution_accuracy'])} | "
        f"{_pct(rates['relaxed_execution_accuracy'])} | {_pct(rates['exact_match_rate'])} | "
        f"{_pct(rates['semantic_match_rate'])} | {rates['avg_latency_ms'] / 1000:.1f} s |"
    )


def render_markdown(run: EvaluationRun) -> str:
    s = summary(run)
    overall = s["overall"]
    settings = run.settings
    passed = overall["execution_accuracy"] >= PASSING_EXECUTION_ACCURACY
    header = "| Group | Cases | Execution accuracy | Relaxed execution | Exact match | Semantic match | Avg latency |"
    rule = "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"

    lines = [
        "# QueryMind text-to-SQL evaluation report",
        "",
        f"Run {run.started_at} → {run.finished_at} (UTC) · test set **{settings['test_set']}** "
        f"(sha256 `{settings['test_set_sha256']}`) · {settings['few_shot_examples']} few-shot examples "
        f"(sha256 `{settings['few_shot_sha256']}`)",
        "",
        f"LLM `{settings['llm']}` · embeddings `{settings['embedding']}` · knowledge base `{settings['collection']}` · "
        f"self-repair attempts {settings['max_repairs']} · row limit {settings['max_rows']} · databases "
        + ", ".join(f"`{name}` ({dialect})" for name, dialect in settings["databases"].items()),
        "",
        "## Summary",
        "",
        "| Metric | Result |",
        "| --- | ---: |",
        f"| **Execution accuracy** (same result set as the ground truth) | **{_pct(overall['execution_accuracy'])}** "
        f"({sum(c.execution_match for c in run.cases)}/{overall['cases']}) |",
        f"| Relaxed execution accuracy (extra columns allowed) | {_pct(overall['relaxed_execution_accuracy'])} |",
        f"| **Exact match rate** (normalised SQL text) | **{_pct(overall['exact_match_rate'])}** |",
        f"| Semantic match rate (exact, or no edits in `sqlglot.diff`) | {_pct(overall['semantic_match_rate'])} |",
        f"| Intent classification accuracy | {_pct(s['intent_accuracy'])} |",
        f"| Guardrails compliance (destructive requests never run) | {_pct(s['guardrail_compliance'])} |",
        f"| Minimum threshold: execution accuracy ≥ 50% | {'met' if passed else 'NOT met'} |",
        "",
        "Outcome of each case: " + ", ".join(f"{status} {count}" for status, count in s["statuses"].items()) + ".",
        "",
        "## Accuracy by query type",
        "",
        header,
        rule,
        *(_rates_row(f"{_TYPE_LABELS.get(t, t)} (`{t}`)", r) for t, r in s["by_query_type"].items()),
        _rates_row("**All**", overall),
        "",
        "## Accuracy by database",
        "",
        header,
        rule,
        *(_rates_row(f"`{name}` ({settings['databases'].get(name, '?')})", r) for name, r in s["by_database"].items()),
        "",
        "## Per-query results",
        "",
        "| ID | Type | DB | Status | Exec | Exact | Semantic | Rows (gen/truth) | Attempts | Notes |",
        "| --- | --- | --- | --- | :---: | :---: | :---: | ---: | ---: | --- |",
    ]
    for case in run.cases:
        rows = f"{case.generated_rows if case.generated_rows is not None else '–'}/{case.ground_truth_rows}"
        semantic = _mark(case.semantic_match) + (
            f" ({case.diff_edits} edits)" if case.diff_edits and case.diff_edits > 0 else ""
        )
        notes = case.reason
        if case.predicted_type and case.predicted_type != case.query_type:
            notes = f"classified {case.predicted_type}; {notes}".strip("; ")
        lines.append(
            f"| {case.id} | {case.query_type.removeprefix('SELECT_').lower()} | {case.database} | {case.status} | "
            f"{_mark(case.execution_match)} | {_mark(case.exact_match)} | {semantic} | {rows} | {case.attempts} | "
            f"{_cell(notes, 90)} |"
        )

    misses = [case for case in run.cases if not case.execution_match]
    lines += ["", "## Execution misses", ""]
    if not misses:
        lines.append("None: every generated query returned the ground-truth result set.")
    for case in misses:
        lines += [
            f"### {case.id} · {case.query_type} · {case.database}",
            "",
            f"**Question:** {case.question}",
            "",
            f"**Why:** {case.reason or case.status}",
            "",
            "Ground truth:",
            "```sql",
            case.ground_truth_sql,
            "```",
            f"Generated ({case.generated_database or 'none'}):",
            "```sql",
            case.generated_sql or "-- no SQL generated",
            "```",
            "",
        ]

    if run.probes:
        lines += [
            "## Guardrails probes",
            "",
            "Destructive requests must never run: they are refused, or an UPDATE is drafted for review "
            "and not executed.",
            "",
            "| ID | Request | Expected | Status | Executed | Compliant | Message |",
            "| --- | --- | --- | --- | :---: | :---: | --- |",
        ]
        lines += [
            f"| {p.id} | {_cell(p.question, 60)} | {p.expect} | {p.status} | {'yes' if p.executed else 'no'} | "
            f"{_mark(p.compliant)} | {_cell(p.message, 80)} |"
            for p in run.probes
        ]
        lines.append("")

    lines += [
        "## Method",
        "",
        "- **Pipeline under test:** the production agent: intent classification, retrieval from Qdrant "
        "(schema, business rules and few-shot examples), SQL generation, guardrail checks, read-only execution "
        "and self-repair. The semantic cache is off, and the final written answer is skipped (it doesn't change "
        "the SQL or the result table).",
        "- **Execution accuracy:** generated and ground-truth SQL run on the same live databases; result sets "
        "compared row by row. Column names are ignored and columns may be in any order; rows compare as a "
        "multiset unless the case sets `order_matters`. Numbers compare numerically (5 = 5.00); non-integral "
        "values match within 0.5% or when one is the other rounded (8.6477 = 8.6). *Relaxed* also accepts "
        "extra columns.",
        "- **Exact match:** both statements normalised by sqlglot (whitespace, keyword/identifier case, quoting, "
        "trailing `;`) and compared as text. **Semantic match:** exact match, or `sqlglot.diff()` finds no edits "
        "after columns are qualified from the live schema, table/column aliases are normalised and, when row "
        "order doesn't matter, a final ORDER BY (without LIMIT) is ignored.",
        "- **Reproduce:** `cd querymind-agentic && uv run querymind evaluate` (add `--validate-only` to check the "
        "ground truth and few-shot SQL without calling the model). Model temperature is 0, but hosted models are "
        "not fully deterministic, so expect small run-to-run differences.",
        "",
    ]
    return "\n".join(lines)


def write_report(run: EvaluationRun, directory: Path) -> tuple[Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    markdown = directory / "report.md"
    data = directory / "results.json"
    markdown.write_text(render_markdown(run), encoding="utf-8")
    data.write_text(json.dumps(run.to_dict(), indent=2, default=str) + "\n", encoding="utf-8")
    return markdown, data
