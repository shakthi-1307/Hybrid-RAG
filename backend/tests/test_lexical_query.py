"""The tsquery expression built from a user's question.

These run without a database: the interesting logic is the translation from
natural language to a query expression, and getting that wrong is silent —
an over-restrictive query returns nothing and looks like "no matching
documents" rather than a bug.
"""

from __future__ import annotations

from app.config import settings
from app.retrieval.lexical_search import build_query_expression, tokenize


def test_tokenizer_lowercases_and_drops_punctuation():
    assert tokenize("Revenue, Recognition!") == ["revenue", "recognition"]


def test_terms_are_combined_with_or_not_and():
    """The important one.

    websearch_to_tsquery ANDs bare terms, so a nine-word question would match
    only chunks containing all nine words. That returns nothing for almost
    every real question, and it fails by finding zero results rather than by
    raising, so nothing points at the cause.
    """
    assert build_query_expression("quarterly revenue policy") == (
        "quarterly or revenue or policy"
    )


def test_repeated_terms_are_collapsed():
    assert build_query_expression("revenue revenue policy") == "revenue or policy"


def test_boolean_words_are_stripped_before_rejoining():
    """ "cats and dogs" is a request for both animals, not a boolean expression."""
    assert build_query_expression("cats and dogs") == "cats or dogs"


def test_punctuation_only_query_yields_no_expression():
    assert build_query_expression("!!! ???") == ""


def test_empty_query_yields_no_expression():
    assert build_query_expression("   ") == ""


def test_term_count_is_capped():
    query = " ".join(f"term{index}" for index in range(settings.MAX_QUERY_TERMS + 25))
    terms = build_query_expression(query).split(" or ")

    assert len(terms) == settings.MAX_QUERY_TERMS


def test_identifiers_survive_tokenisation():
    """Error codes are the case dense retrieval handles worst, so lexical
    search has to keep them intact."""
    assert build_query_expression("error E-4471") == "error or e or 4471"
