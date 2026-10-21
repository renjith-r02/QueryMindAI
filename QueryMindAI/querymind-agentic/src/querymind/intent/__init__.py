"""Classify a question's intent before SQL is generated.

SELECT_* questions are answered as before; UPDATE requests get SQL that is returned but never
executed; DELETE, INSERT, DDL and permission changes are refused before reaching the generator.
"""

from querymind.intent.classifier import IntentClassifier
from querymind.intent.models import DESCRIPTIONS, SELECT_TYPES, Intent, IntentClassification, QueryType

__all__ = ["DESCRIPTIONS", "SELECT_TYPES", "Intent", "IntentClassification", "IntentClassifier", "QueryType"]
