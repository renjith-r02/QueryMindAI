"""Run the test set through the real pipeline and score it.

For each case the agent answers the question the way users get answers (intent
classification, retrieval with few-shot examples, SQL generation, guardrail checks, execution
and up to `max_repairs` self-repairs), without the semantic cache and without writing the
final prose answer. The ground-truth SQL runs on the same databases, and the two result tables
and statements are compared (see `compare`).
"""

from __future__ import annotations

import datetime as dt
import logging
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import inspect

from querymind.agent.sql_agent import QueryMindAgent
from querymind.database.executor import DatabaseRegistry, QueryResult
from querymind.evaluation.compare import compare_results, exact_match, semantic_match
from querymind.evaluation.dataset import (
    DEFAULT_FEW_SHOT,
    DEFAULT_TEST_SET,
    QUERY_TYPES,
    FewShotExample,
    TestCase,
    file_digest,
    load_few_shot,
    load_test_set,
)
from querymind.service import QueryMindService

logger = logging.getLogger(__name__)


@dataclass
class CaseResult:
    id: str
    query_type: str
    database: str
    question: str
    ground_truth_sql: str
    status: str = "error"  # the agent's status: answered, not_answerable, failed, blocked, generated, error
    generated_sql: str | None = None
    generated_database: str | None = None
    queries_generated: int = 0
    attempts: int = 0
    predicted_type: str | None = None
    execution_match: bool = False
    relaxed_execution_match: bool = False
    exact_match: bool = False
    semantic_match: bool = False
    diff_edits: int | None = None
    ground_truth_rows: int | None = None
    generated_rows: int | None = None
    reason: str = ""
    latency_ms: float = 0.0


@dataclass
class ProbeResult:
    id: str
    question: str
    expect: str
    status: str
    compliant: bool
    executed: bool
    message: str = ""


@dataclass
class EvaluationRun:
    started_at: str
    finished_at: str
    settings: dict[str, Any]
    cases: list[CaseResult]
    probes: list[ProbeResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "summary": summary(self)}


@dataclass
class ValidationIssue:
    source: str  # "test_set" or "few_shot"
    id: str
    problem: str


# -- scoring --------------------------------------------------------------------------------


def _rates(cases: list[CaseResult]) -> dict[str, Any]:
    n = len(cases)

    def rate(flag: str) -> float:
        return round(sum(getattr(case, flag) for case in cases) / n, 4) if n else 0.0

    return {
        "cases": n,
        "execution_accuracy": rate("execution_match"),
        "relaxed_execution_accuracy": rate("relaxed_execution_match"),
        "exact_match_rate": rate("exact_match"),
        "semantic_match_rate": rate("semantic_match"),
        "avg_latency_ms": round(sum(c.latency_ms for c in cases) / n, 1) if n else 0.0,
    }


def summary(run: EvaluationRun) -> dict[str, Any]:
    by_type = {t: _rates([c for c in run.cases if c.query_type == t]) for t in QUERY_TYPES}
    databases = sorted({c.database for c in run.cases})
    by_database = {d: _rates([c for c in run.cases if c.database == d]) for d in databases}
    probes = run.probes
    return {
        "overall": _rates(run.cases),
        "by_query_type": {t: rates for t, rates in by_type.items() if rates["cases"]},
        "by_database": by_database,
        "intent_accuracy": round(sum(c.predicted_type == c.query_type for c in run.cases) / len(run.cases), 4)
        if run.cases
        else 0.0,
        "guardrail_compliance": round(sum(p.compliant for p in probes) / len(probes), 4) if probes else None,
        "statuses": {s: sum(c.status == s for c in run.cases) for s in sorted({c.status for c in run.cases})},
    }


# -- running --------------------------------------------------------------------------------


def schema_for_sqlglot(databases: DatabaseRegistry, name: str) -> dict:
    """Column types for sqlglot.qualify: {table: {column: type}} for MySQL (one schema per
    database), {schema: {table: {column: type}}} for PostgreSQL."""
    inspector = inspect(databases.engine(name))
    default = inspector.default_schema_name
    mysql = databases.dialect(name) == "mysql"
    mapping: dict = {}
    for schema in inspector.get_schema_names():
        if schema in {"information_schema", "pg_catalog", "pg_toast", "mysql", "performance_schema", "sys"}:
            continue
        if mysql and schema != default:
            continue
        for table in inspector.get_table_names(schema=schema) + inspector.get_view_names(schema=schema):
            columns = {c["name"]: str(c["type"]) for c in inspector.get_columns(table, schema=schema)}
            if mysql:
                mapping[table] = columns
            else:
                mapping.setdefault(schema, {})[table] = columns
    return mapping


class Evaluator:
    def __init__(
        self,
        service: QueryMindService,
        max_repairs: int = 2,
        on_case: Callable[[CaseResult], None] = lambda _: None,
    ):
        self.service = service
        self.max_repairs = max_repairs
        self.on_case = on_case
        self.guardrails = service.guardrails()
        self.databases = service.databases.with_limits(
            self.guardrails.max_rows, service.settings.query_timeout, self.guardrails
        )
        self._schemas: dict[str, dict | None] = {}

    def agent(self) -> QueryMindAgent:
        # No semantic cache: every case must be generated by the model.
        return QueryMindAgent(self.service.rag(self.guardrails), self.databases, max_repairs=self.max_repairs)

    def schema(self, name: str) -> dict | None:
        if name not in self._schemas:
            try:
                self._schemas[name] = schema_for_sqlglot(self.databases, name)
            except Exception as error:  # noqa: BLE001 - only used to normalise SQL
                logger.warning("Could not read the schema of %s for sqlglot: %s", name, error)
                self._schemas[name] = None
        return self._schemas[name]

    def run(
        self,
        test_set_path: Path = DEFAULT_TEST_SET,
        few_shot_path: Path = DEFAULT_FEW_SHOT,
        ids: set[str] | None = None,
        probes: bool = True,
    ) -> EvaluationRun:
        test_set = load_test_set(test_set_path)
        started = _now()
        cases = [self.evaluate_case(case) for case in test_set.cases if not ids or case.id in ids]
        probe_results = [
            self.evaluate_probe(probe.id, probe.question, probe.expect)
            for probe in test_set.guardrail_probes
            if probes and (not ids or probe.id in ids)
        ]
        settings = self.service.settings
        return EvaluationRun(
            started_at=started,
            finished_at=_now(),
            settings={
                "llm": f"{settings.llm_provider}:{settings.resolved_llm_model}",
                "embedding": f"{settings.embedding_provider}:{self.service.store.embedder.model_name}",
                "collection": settings.collection,
                "max_repairs": self.max_repairs,
                "max_rows": self.guardrails.max_rows,
                "guardrail_policy_version": self.guardrails.version,
                "test_set": f"{test_set.name} v{test_set.version}",
                "test_set_sha256": file_digest(test_set_path),
                "few_shot_examples": len(load_few_shot(few_shot_path)) if Path(few_shot_path).exists() else 0,
                "few_shot_sha256": file_digest(few_shot_path) if Path(few_shot_path).exists() else None,
                "databases": {name: self.databases.dialect(name) for name in self.databases.names},
            },
            cases=cases,
            probes=probe_results,
        )

    def evaluate_case(self, case: TestCase) -> CaseResult:
        result = CaseResult(case.id, case.query_type, case.database, case.question, case.ground_truth_sql)
        expected = self.databases.execute(case.database, case.ground_truth_sql)
        result.ground_truth_rows = len(expected.rows) if expected.ok else None
        started = time.perf_counter()
        try:
            answer = self.agent().run(case.question, summarize=False)
        except Exception as error:  # noqa: BLE001 - one failing case must not stop the run
            logger.exception("Case %s failed", case.id)
            result.reason = f"{type(error).__name__}: {error}"
            result.latency_ms = _elapsed(started)
            self.on_case(result)
            return result
        result.latency_ms = _elapsed(started)
        result.status = answer.status
        result.attempts = len(answer.attempts)
        result.predicted_type = answer.intent.query_type if answer.intent else None
        plan = answer.plan
        if plan is not None and plan.queries:
            result.queries_generated = len(plan.queries)
            result.generated_sql = (
                plan.queries[0].sql if len(plan.queries) == 1 else "\n;\n".join(q.sql for q in plan.queries)
            )
            result.generated_database = ", ".join(sorted({q.database for q in plan.queries}))
            if len(plan.queries) == 1 and plan.queries[0].database.lower() == case.database.lower():
                result.exact_match = exact_match(plan.queries[0].sql, case.ground_truth_sql, case.dialect)
                result.semantic_match, result.diff_edits = semantic_match(
                    plan.queries[0].sql,
                    case.ground_truth_sql,
                    case.dialect,
                    self.schema(case.database),
                    ignore_order=not case.order_matters,
                )

        table: QueryResult | None = answer.result
        if answer.status != "answered" or table is None:
            result.reason = _failure(answer)
        else:
            result.generated_rows = len(table.rows)
            comparison = compare_results(expected, table, case.order_matters)
            result.execution_match = comparison.match
            result.relaxed_execution_match = comparison.relaxed_match
            result.reason = comparison.reason
        self.on_case(result)
        return result

    def evaluate_probe(self, probe_id: str, question: str, expect: str) -> ProbeResult:
        """A destructive request must never run: refused, or (UPDATE) drafted for review only."""
        try:
            answer = self.agent().run(question, summarize=False)
        except Exception as error:  # noqa: BLE001
            # Unknown outcome: counted as not compliant so it gets looked at.
            return ProbeResult(probe_id, question, expect, "error", False, False, f"{type(error).__name__}: {error}")
        executed = any(attempt.results for attempt in answer.attempts)
        compliant = not executed and answer.status in {"blocked", "generated", "not_answerable", "failed"}
        message = (answer.intent.blocked_message if answer.intent else None) or "; ".join(answer.warnings)
        return ProbeResult(probe_id, question, expect, answer.status, compliant, executed, message or "")


def validate(
    service: QueryMindService, test_set_path: Path = DEFAULT_TEST_SET, few_shot_path: Path = DEFAULT_FEW_SHOT
) -> tuple[int, list[ValidationIssue]]:
    """Run every ground-truth and few-shot SELECT on the live databases (no model calls).

    Returns the number of statements checked and the problems found: errors, empty results
    (for ground truth), unknown databases, and UPDATE drafts the guardrails would withhold."""
    guardrails = service.guardrails()
    databases = service.databases.with_limits(guardrails.max_rows, service.settings.query_timeout, guardrails)
    issues: list[ValidationIssue] = []
    checked = 0
    for case in load_test_set(test_set_path).cases:
        checked += 1
        outcome = databases.execute(case.database, case.ground_truth_sql)
        if not outcome.ok:
            issues.append(ValidationIssue("test_set", case.id, outcome.error or "failed"))
        elif not outcome.rows:
            issues.append(ValidationIssue("test_set", case.id, "ground truth returns no rows"))
    examples: list[FewShotExample] = load_few_shot(few_shot_path) if Path(few_shot_path).exists() else []
    for example in examples:
        checked += 1
        if example.query_type == "UPDATE":
            if reason := guardrails.check_update(example.sql):
                issues.append(ValidationIssue("few_shot", example.id, f"UPDATE draft would be withheld: {reason}"))
            continue
        outcome = databases.execute(example.database, example.sql)
        if not outcome.ok:
            issues.append(ValidationIssue("few_shot", example.id, outcome.error or "failed"))
    return checked, issues


def _failure(answer) -> str:
    if answer.status == "blocked":
        return "refused by guardrails/intent: " + ((answer.intent and answer.intent.blocked_message) or "")
    errors = [error.error for attempt in answer.attempts for error in attempt.errors if error.error]
    if errors:
        return f"{answer.status}: {errors[-1]}"
    if answer.plan is not None and not answer.plan.answerable:
        return f"{answer.status}: model said not answerable ({answer.plan.explanation})"
    return answer.status


def _now() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds")


def _elapsed(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 1)
