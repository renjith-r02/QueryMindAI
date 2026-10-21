import pytest
from qdrant_client import QdrantClient

from querymind.cache import SemanticCache
from support.fakes import HashingEmbedder

EMBED = HashingEmbedder()
SCOPE = "llm=x|db=*"


class Clock:
    def __init__(self):
        self.now = 1_000_000.0

    def __call__(self):
        return self.now


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def cache(clock):
    return SemanticCache(QdrantClient(":memory:"), "kb_cache", threshold=0.9, ttl_seconds=600, clock=clock)


def put(cache, question, scope=SCOPE, answer="a"):
    cache.store(EMBED.embed_query(question), question, scope, {"answer": answer})


def get(cache, question, scope=SCOPE):
    return cache.lookup(EMBED.embed_query(question), question, scope)


def test_empty_cache_misses_without_creating_anything(cache):
    assert get(cache, "anything") is None
    assert cache.stats().entries == 0


def test_exact_and_near_identical_questions_hit(cache):
    put(cache, "How many orders per status?", answer="by status")
    hit = get(cache, "how many orders per status")
    assert hit is not None and hit.payload == {"answer": "by status"}
    assert hit.similarity > 0.99 and hit.question == "How many orders per status?"
    assert hit.info()["hit"] is True


def test_different_questions_miss(cache):
    put(cache, "How many orders per status?")
    assert get(cache, "Which customers live in Boston") is None


def test_constraints_must_match_even_when_similar(cache):
    put(cache, "Top 5 products by revenue last month")
    assert get(cache, "Top 5 products by revenue last month") is not None
    assert get(cache, "Top 10 products by revenue last month") is None
    assert get(cache, "Top 5 products by revenue this month") is None


def test_scope_must_match(cache):
    put(cache, "orders per status", scope="llm=a|db=*")
    assert get(cache, "orders per status", scope="llm=b|db=*") is None
    assert get(cache, "orders per status", scope="llm=a|db=returns_db") is None


def test_entries_expire(cache, clock):
    put(cache, "orders per status")
    clock.now += 599
    assert get(cache, "orders per status") is not None
    clock.now += 2
    assert get(cache, "orders per status") is None


def test_storing_replaces_the_same_question_and_drops_expired(cache, clock):
    put(cache, "orders per status", answer="old")
    put(cache, "Orders per status!", answer="new")  # same normalized question -> same entry
    assert cache.stats().entries == 1
    assert get(cache, "orders per status").payload == {"answer": "new"}

    clock.now += 601
    put(cache, "returns by reason")
    assert cache.stats().entries == 1  # the expired entry was removed


def test_clear_and_stats(cache):
    put(cache, "orders per status")
    stats = cache.stats()
    assert (stats.enabled, stats.entries, stats.threshold, stats.ttl_seconds) == (True, 1, 0.9, 600)
    cache.clear()
    assert cache.stats().entries == 0 and get(cache, "orders per status") is None


def test_embedding_size_change_starts_over(cache):
    put(cache, "orders per status")
    small = [1.0, 0.0, 0.0]
    assert cache.lookup(small, "orders per status", SCOPE) is None  # old entries are unusable
    cache.store(small, "orders per status", SCOPE, {"answer": "3d"})
    assert cache.lookup(small, "orders per status", SCOPE).payload == {"answer": "3d"}


def test_threshold_is_validated():
    with pytest.raises(ValueError):
        SemanticCache(QdrantClient(":memory:"), "c", threshold=0)


def test_normalized_identical_question_hits_even_below_the_threshold(clock):
    strict = SemanticCache(QdrantClient(":memory:"), "c", threshold=1.0, ttl_seconds=600, clock=clock)
    question, variant = "How many orders per status?", "how many orders, per status"
    strict.store([1.0, 0.0, 0.0], question, SCOPE, {"answer": "a"})
    # a vector far from the stored one: only the normalized-text path can match
    hit = strict.lookup([0.0, 1.0, 0.0], variant, SCOPE)
    assert hit is not None and hit.similarity == 1.0
    assert strict.lookup([0.0, 1.0, 0.0], variant, "other scope") is None
    clock.now += 601
    assert strict.lookup([0.0, 1.0, 0.0], variant, SCOPE) is None  # expired
