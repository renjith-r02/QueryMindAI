import pytest

from querymind.intent.rules import classify_heuristically, looks_like_update, mentioned, prohibited

TABLES = ["orders", "order_lines", "products", "users"]
COLUMNS = ["orders.placed_at", "orders.status", "order_lines.line_total", "products.name", "users.email"]


@pytest.mark.parametrize(
    "question",
    [
        "Delete all cancelled orders",
        "please delete the test users",
        "Could you remove the orders from 2019?",
        "purge old carts",
        "get rid of duplicate customers",
        "show me the cancelled orders and then delete them",
        "DELETE FROM orders WHERE status = 'cancelled'",
        "truncate table order_lines",
        "drop table products",
        "Can you alter table users add column age",
        "insert into products values (1, 'x')",
        "add a new row for customer Bob",
        "grant select on orders to analyst",
    ],
)
def test_prohibited_requests_are_refused(question):
    assert prohibited(question)


def test_delete_message_mentions_update_drafts():
    assert "Deleting data is not allowed" in prohibited("delete every order")


@pytest.mark.parametrize(
    "question",
    [
        "How many orders were deleted last month?",  # past tense about data, not a request
        "Which products were removed from the catalog this year?",
        "Show the latest update date per order",
        "Top 10 products by revenue",
        "list users created after 2025-01-01",
    ],
)
def test_read_questions_are_not_refused(question):
    assert prohibited(question) is None


@pytest.mark.parametrize(
    "question,expected",
    [
        ("Update order 1042 status to shipped", True),
        ("Please change the price of SKU FIT-02 to 49.99", True),
        ("mark order 7 as delivered", True),
        ("Could you increase all prices in Shoes by 5%?", True),
        ("Show orders by status", False),
    ],
)
def test_update_detection(question, expected):
    assert looks_like_update(question) is expected


def test_mentioned_matches_names_plurals_and_underscores():
    found = mentioned("total line totals of orders by product name", [*TABLES, *COLUMNS])
    assert found == ["orders", "products", "order_lines.line_total", "products.name"]


@pytest.mark.parametrize(
    "question,query_type,traits",
    [
        ("list the email of every user", "SELECT_SIMPLE", []),
        ("how many orders per status", "SELECT_AGGREGATE", ["aggregate"]),
        ("orders placed last month", "SELECT_TEMPORAL", ["temporal"]),
        ("total revenue by month this year", "SELECT_TEMPORAL", ["aggregate", "temporal"]),
        ("email of users with their orders", "SELECT_JOIN", ["join"]),
        ("update order 5 status to shipped", "UPDATE", []),
        ("delete order 5", "UNSUPPORTED", []),
    ],
)
def test_heuristic_classification(question, query_type, traits):
    intent = classify_heuristically(question, TABLES, COLUMNS)
    assert intent.query_type == query_type
    assert intent.traits == traits
    assert intent.blocked == (query_type == "UNSUPPORTED")
