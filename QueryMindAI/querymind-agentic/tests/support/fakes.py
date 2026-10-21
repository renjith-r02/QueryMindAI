"""Offline stand-ins for the embedding model and the LLM."""

import hashlib
import math
import re
from pathlib import Path

from querymind.agent import FinalAnswer, GeneratedQuery, SqlAnswer
from querymind.intent import IntentClassification

SQLS = Path(__file__).resolve().parents[2] / "sqls"


class HashingEmbedder:
    """Deterministic bag-of-words embedder so retrieval works offline."""

    model_name = "hashing-test"

    def _vector(self, text):
        vector = [0.0] * 256
        for word in re.findall(r"\w+", text.lower()):
            vector[int(hashlib.md5(word.encode()).hexdigest(), 16) % 256] += 1.0
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]

    def embed_documents(self, texts):
        return [self._vector(t) for t in texts]

    def embed_query(self, text):
        return self._vector(text)


class ScriptedLLM:
    """Classifies with `intent`, returns queued SqlAnswer plans, then a FinalAnswer; records every call."""

    model_name = "scripted"

    def __init__(self, *plans, intent=None):
        self.plans = list(plans)
        self.intent = intent or IntentClassification(
            query_type="SELECT_SIMPLE", traits=[], tables_mentioned=[], columns_mentioned=[], reason="scripted"
        )
        self.prompts = []  # prompts of SQL generation and final-answer calls
        self.systems = []  # system instruction of each SQL generation call
        self.classified = []  # questions sent to the intent classifier

    def generate(self, system, prompt, schema):
        if schema is IntentClassification:
            self.classified.append(prompt)
            return self.intent
        self.prompts.append(prompt)
        if schema is FinalAnswer:
            return FinalAnswer(answer="final", caveats=[])
        self.systems.append(system)
        return self.plans.pop(0)


def intent(query_type, traits=(), tables=(), columns=(), reason="scripted"):
    return IntentClassification(
        query_type=query_type,
        traits=list(traits),
        tables_mentioned=list(tables),
        columns_mentioned=list(columns),
        reason=reason,
    )


def plan(*queries, merge_sql=None, answerable=True):
    return SqlAnswer(
        answerable=answerable,
        queries=[GeneratedQuery(database=db, dialect="sqlite", sql=sql, purpose="p") for db, sql in queries],
        merge_sql=merge_sql,
        explanation="approach",
        assumptions=["all time"],
        sources=["S1"],
    )
