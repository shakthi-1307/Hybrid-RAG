from __future__ import annotations

from evaluation.citation_metrics import hallucinated_markers, summarise
from evaluation.schema import AnswerRecord

CONTEXTS = ["passage one", "passage two", "passage three"]


def record(emitted: list[int], valid: list[int]) -> AnswerRecord:
    return AnswerRecord(
        question="q",
        answer="a",
        contexts=CONTEXTS,
        context_sections=["Doc | Section"] * len(CONTEXTS),
        emitted_markers=emitted,
        valid_markers=valid,
    )


def test_markers_outside_the_context_are_flagged():
    """The model cited [7] when only three sources were supplied."""
    assert hallucinated_markers(record([1, 7], [1])) == [7]


def test_fully_grounded_answer_flags_nothing():
    assert hallucinated_markers(record([1, 2], [1, 2])) == []


def test_hallucination_rate_is_over_emitted_markers_not_answers():
    metrics = summarise([record([1, 7], [1]), record([2], [2])])

    assert metrics.emitted_marker_count == 3
    assert metrics.hallucinated_marker_count == 1
    assert metrics.hallucinated_marker_rate == 1 / 3


def test_coverage_counts_answers_with_at_least_one_valid_citation():
    metrics = summarise([record([1], [1]), record([], []), record([9], [])])

    assert metrics.answers_with_citations == 1 / 3


def test_mean_citations_counts_only_valid_ones():
    metrics = summarise([record([1, 2, 9], [1, 2]), record([1], [1])])

    assert metrics.mean_citations_per_answer == 1.5


def test_answer_citing_nothing_does_not_divide_by_zero():
    metrics = summarise([record([], [])])

    assert metrics.hallucinated_marker_rate == 0.0


def test_empty_run_is_all_zeroes():
    metrics = summarise([])

    assert metrics.answers_with_citations == 0.0
    assert metrics.emitted_marker_count == 0
