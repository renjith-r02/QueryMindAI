"""Evaluation harness for text-to-SQL: execution accuracy and exact/semantic match on a test set
with ground-truth SQL, broken down by query type and database (see `harness`)."""

from querymind.evaluation.compare import compare_results, exact_match, normalise_sql, semantic_match
from querymind.evaluation.dataset import (
    DEFAULT_FEW_SHOT,
    DEFAULT_REPORTS,
    DEFAULT_TEST_SET,
    FewShotExample,
    GuardrailProbe,
    TestCase,
    TestSet,
    load_few_shot,
    load_test_set,
)
from querymind.evaluation.harness import CaseResult, EvaluationRun, Evaluator, ProbeResult, summary, validate
from querymind.evaluation.report import render_markdown, write_report

__all__ = [
    "DEFAULT_FEW_SHOT",
    "DEFAULT_REPORTS",
    "DEFAULT_TEST_SET",
    "CaseResult",
    "EvaluationRun",
    "Evaluator",
    "FewShotExample",
    "GuardrailProbe",
    "ProbeResult",
    "TestCase",
    "TestSet",
    "compare_results",
    "exact_match",
    "load_few_shot",
    "load_test_set",
    "normalise_sql",
    "render_markdown",
    "semantic_match",
    "summary",
    "validate",
    "write_report",
]
