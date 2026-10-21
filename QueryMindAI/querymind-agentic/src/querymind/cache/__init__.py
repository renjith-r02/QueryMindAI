"""Semantic cache: answer repeated or near-identical questions without calling the LLM."""

from querymind.cache.fingerprint import fingerprint, normalize
from querymind.cache.semantic_cache import CacheHit, CacheStats, SemanticCache

__all__ = ["CacheHit", "CacheStats", "SemanticCache", "fingerprint", "normalize"]
