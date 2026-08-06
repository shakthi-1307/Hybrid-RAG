from __future__ import annotations

import pytest

from evaluation.metrics import (
    first_relevant_rank,
    matches_expected,
    ndcg_at_k,
    normalise,
    percentile,
    reciprocal_rank,
    wilson_interval,
)

TOP_K = 6
RETRIEVED = [
    "Introduction",
    "Billing > Refunds",
    "Appendix > Glossary",
]


def test_normalise_collapses_whitespace_and_case():
    assert normalise("  Billing   >  REFUNDS \n") == "billing > refunds"


def test_expected_section_matches_a_fuller_heading_path():
    """Gold records 'Refunds'; retrieval returns the full path."""
    assert matches_expected("Refunds", "Billing > Refunds")


def test_unrelated_section_does_not_match():
    assert not matches_expected("Refunds", "Billing > Invoices")


def test_rank_is_one_based_and_finds_the_first_match():
    assert first_relevant_rank("Refunds", RETRIEVED) == 2


def test_missing_section_has_no_rank():
    assert first_relevant_rank("Shipping", RETRIEVED) is None


def test_reciprocal_rank_rewards_earlier_positions():
    assert reciprocal_rank(1) == 1.0
    assert reciprocal_rank(2) == 0.5
    assert reciprocal_rank(None) == 0.0


def test_ndcg_distinguishes_rank_one_from_rank_six():
    """Hit rate cannot tell these apart; this is what shows reranking works."""
    assert ndcg_at_k(1, TOP_K) == 1.0
    assert ndcg_at_k(6, TOP_K) < ndcg_at_k(2, TOP_K) < 1.0


def test_ndcg_is_zero_beyond_the_cutoff_or_when_absent():
    assert ndcg_at_k(TOP_K + 1, TOP_K) == 0.0
    assert ndcg_at_k(None, TOP_K) == 0.0


def test_wilson_interval_brackets_the_observed_rate():
    low, high = wilson_interval(27, 30)

    assert low < 27 / 30 < high


def test_wilson_interval_is_wider_for_smaller_samples():
    narrow_low, narrow_high = wilson_interval(270, 300)
    wide_low, wide_high = wilson_interval(27, 30)

    assert (wide_high - wide_low) > (narrow_high - narrow_low)


def test_wilson_interval_stays_within_zero_and_one():
    low, high = wilson_interval(30, 30)

    assert low >= 0.0
    assert high <= 1.0


def test_wilson_interval_handles_an_empty_sample():
    assert wilson_interval(0, 0) == (0.0, 0.0)


@pytest.mark.parametrize(
    ("fraction", "expected"),
    [(0.5, 30.0), (0.95, 50.0)],
)
def test_percentile_uses_nearest_rank(fraction, expected):
    assert percentile([10.0, 20.0, 30.0, 40.0, 50.0], fraction) == expected


def test_percentile_of_nothing_is_zero():
    assert percentile([], 0.5) == 0.0
