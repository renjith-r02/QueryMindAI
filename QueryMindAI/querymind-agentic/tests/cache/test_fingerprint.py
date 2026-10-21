import pytest

from querymind.cache import fingerprint, normalize


def test_normalize_ignores_case_punctuation_and_spacing():
    assert normalize("  Top 5 products, by REVENUE?? ") == normalize("top 5 products by revenue")


@pytest.mark.parametrize(
    "a,b",
    [
        ("Top 5 products by revenue", "top 5 products by revenue?"),
        ("How many orders per status", "how many orders are there per status"),
        ("revenue last month", "What was the revenue last month"),
    ],
)
def test_same_constraints_match(a, b):
    assert fingerprint(a) == fingerprint(b)


@pytest.mark.parametrize(
    "a,b",
    [
        ("Top 5 products by revenue", "Top 10 products by revenue"),
        ("revenue last month", "revenue this month"),
        ("revenue in 2025", "revenue in 2026"),
        ("highest priced products", "lowest priced products"),
        ("orders with a coupon", "orders without a coupon"),
        ("orders in status 'shipped'", "orders in status 'returned'"),
        ("average order value", "total order value"),
        ("customers who ordered more than 3 times", "customers who ordered less than 3 times"),
    ],
)
def test_different_constraints_differ(a, b):
    assert fingerprint(a) != fingerprint(b)


def test_numbers_are_normalised():
    assert fingerprint("orders over 1,000 dollars") == fingerprint("orders over 1000 dollars")
