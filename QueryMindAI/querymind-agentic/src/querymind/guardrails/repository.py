"""Store the guardrail policy in a Qdrant collection (one record; no vectors are needed)."""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable

from qdrant_client import QdrantClient, models

from querymind.exceptions import QueryMindError
from querymind.guardrails.policy import (
    GuardrailPolicy,
    GuardrailPolicyInput,
    baseline_problems,
    default_policy,
    with_baseline,
)

POLICY_ID = str(uuid.uuid5(uuid.NAMESPACE_URL, "querymind:guardrails"))


class GuardrailPolicyError(QueryMindError, ValueError):
    """The policy would weaken the baseline guardrails."""


class GuardrailRepository:
    def __init__(
        self,
        client: QdrantClient,
        collection: str,
        default: Callable[[], GuardrailPolicyInput] = default_policy,
        clock: Callable[[], float] = time.time,
        on_change: Callable[[], None] = lambda: None,
    ):
        """`default` is saved the first time the policy is read; `on_change` is called after every save."""
        self.client = client
        self.collection = collection
        self.default = default
        self.clock = clock
        self.on_change = on_change
        self._lock = threading.Lock()
        self._ready = False

    def get(self) -> GuardrailPolicy:
        self._ensure_collection()
        points = self.client.retrieve(self.collection, ids=[POLICY_ID], with_payload=True)
        if points:
            return with_baseline(GuardrailPolicy.model_validate(points[0].payload))
        with self._lock:
            return self._save(self.default())

    def save(self, data: GuardrailPolicyInput) -> GuardrailPolicy:
        """Replace the policy. Raises GuardrailPolicyError if it removes or disables part of the baseline."""
        if problems := baseline_problems(data):
            message = "; ".join(problems)
            raise GuardrailPolicyError(message[0].upper() + message[1:] + ".")
        self._ensure_collection()
        with self._lock:
            policy = self._save(data)
        self.on_change()
        return policy

    def reset(self) -> GuardrailPolicy:
        """Restore the built-in policy."""
        return self.save(self.default())

    def _save(self, data: GuardrailPolicyInput) -> GuardrailPolicy:
        policy = with_baseline(GuardrailPolicy(**data.model_dump(), updated_at=self.clock()))
        self.client.upsert(
            self.collection,
            points=[models.PointStruct(id=POLICY_ID, vector={}, payload=policy.model_dump(mode="json"))],
            wait=True,
        )
        return policy

    def _ensure_collection(self) -> None:
        if not self._ready:
            if not self.client.collection_exists(self.collection):
                self.client.create_collection(self.collection, vectors_config={})
            self._ready = True
