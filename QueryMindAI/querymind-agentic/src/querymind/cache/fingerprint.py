"""The parts of a question that must match exactly for a cached answer to be reused.

Embeddings of "top 5 products last month" and "top 10 products this month" are nearly
identical, but the answers differ. Numbers, quoted values, time words and direction or
negation words change the answer, so they are compared exactly on top of the similarity.
"""

from __future__ import annotations

import re

_NUMBER = re.compile(r"(?<![\w.])-?\d+(?:[.,]\d+)*%?")
_QUOTED = re.compile(r"\"([^\"]+)\"|'([^']+)'|`([^`]+)`")
_WORDS = {
    # time
    "today", "yesterday", "tomorrow", "now", "current", "currently", "last", "this", "next", "previous",
    "past", "since", "before", "after", "between", "ago", "day", "days", "daily", "week", "weeks", "weekly",
    "month", "months", "monthly", "quarter", "quarters", "quarterly", "year", "years", "yearly", "annual",
    "ytd", "mtd", "q1", "q2", "q3", "q4", "january", "february", "march", "april", "may", "june", "july",
    "august", "september", "october", "november", "december", "weekend", "weekday", "hour", "hours",
    # direction and ranking
    "top", "bottom", "highest", "lowest", "most", "least", "max", "min", "maximum", "minimum", "first",
    "latest", "earliest", "oldest", "newest", "ascending", "descending", "asc", "desc", "increase", "decrease",
    "more", "less", "fewer", "above", "below", "over", "under", "greater", "smaller",
    # negation and exclusion
    "not", "no", "without", "except", "excluding", "exclude", "never", "non", "only",
    # measures that are easy to confuse
    "average", "avg", "mean", "median", "sum", "total", "count", "number", "percentage", "percent", "rate",
    "ratio", "share", "net", "gross",
}  # fmt: skip
_TOKEN = re.compile(r"[a-z0-9]+")


def normalize(question: str) -> str:
    """Lower case, punctuation removed, single spaces: equal for trivially different spellings."""
    return " ".join(_TOKEN.findall(question.lower()))


def fingerprint(question: str) -> str:
    """Numbers, quoted values and answer-changing words, in order of appearance."""
    lowered = question.lower()
    parts = [next(group for group in match.groups() if group).strip() for match in _QUOTED.finditer(lowered)]
    unquoted = _QUOTED.sub(" ", lowered)
    parts += [number.replace(",", "") for number in _NUMBER.findall(unquoted)]
    parts += [word for word in _TOKEN.findall(unquoted) if word in _WORDS]
    return "|".join(parts)
