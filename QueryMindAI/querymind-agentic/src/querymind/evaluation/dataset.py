"""The evaluation test set and the few-shot library, as typed models."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from querymind.config import PROJECT_DIR

DEFAULT_TEST_SET = PROJECT_DIR / "evaluation" / "test_set.json"
DEFAULT_FEW_SHOT = PROJECT_DIR / "sqls" / "few_shot_examples.json"
DEFAULT_REPORTS = PROJECT_DIR / "evaluation" / "reports"

SelectType = Literal["SELECT_SIMPLE", "SELECT_AGGREGATE", "SELECT_JOIN", "SELECT_TEMPORAL"]
QUERY_TYPES: tuple[str, ...] = ("SELECT_SIMPLE", "SELECT_AGGREGATE", "SELECT_JOIN", "SELECT_TEMPORAL")


class TestCase(BaseModel):
    __test__ = False  # not a pytest class
    model_config = ConfigDict(extra="forbid")

    id: str
    query_type: SelectType
    database: str
    dialect: Literal["mysql", "postgresql", "sqlite"]
    question: str = Field(min_length=1)
    ground_truth_sql: str = Field(min_length=1)
    order_matters: bool = Field(default=False, description="Compare rows in order (else as a multiset)")
    notes: str | None = None


class GuardrailProbe(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    question: str = Field(min_length=1)
    expect: Literal["blocked", "drafted"] = Field(
        default="blocked", description="blocked: refused; drafted: an UPDATE returned for review, never run"
    )


class TestSet(BaseModel):
    __test__ = False  # not a pytest class
    model_config = ConfigDict(extra="forbid")

    name: str
    version: int = 1
    description: str = ""
    cases: list[TestCase]
    guardrail_probes: list[GuardrailProbe] = Field(default_factory=list)

    @model_validator(mode="after")
    def _unique_ids(self) -> TestSet:
        ids = [case.id for case in self.cases] + [probe.id for probe in self.guardrail_probes]
        if duplicates := sorted({i for i in ids if ids.count(i) > 1}):
            raise ValueError(f"duplicate ids: {', '.join(duplicates)}")
        return self


class FewShotExample(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    query_type: Literal["SELECT_SIMPLE", "SELECT_AGGREGATE", "SELECT_JOIN", "SELECT_TEMPORAL", "UPDATE"]
    database: str
    dialect: str
    question: str
    sql: str
    notes: str | None = None


def load_test_set(path: Path = DEFAULT_TEST_SET) -> TestSet:
    return TestSet.model_validate_json(Path(path).read_text(encoding="utf-8"))


def load_few_shot(path: Path = DEFAULT_FEW_SHOT) -> list[FewShotExample]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    pairs = data["pairs"] if isinstance(data, dict) else data
    return [FewShotExample.model_validate(pair) for pair in pairs]


def file_digest(path: Path) -> str:
    """Short SHA-256 of a file, so a report records exactly which inputs it used."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:12]
