"""Citation metrics computed by counting, not by asking a model.

RAGAS scores faithfulness with an LLM judge, which is useful but probabilistic.
These numbers are exact: either the model emitted a marker pointing outside the
supplied context or it did not. The pipeline discards those markers before they
reach the user, so this measures how often that guard actually fires.
"""

from __future__ import annotations

from evaluation.schema import AnswerRecord, CitationMetrics


def hallucinated_markers(record: AnswerRecord) -> list[int]:
    """Markers the model emitted that pointed outside the supplied context."""
    valid = set(record.valid_markers)
    return [marker for marker in record.emitted_markers if marker not in valid]


def summarise(records: list[AnswerRecord]) -> CitationMetrics:
    if not records:
        return CitationMetrics(
            answers_with_citations=0.0,
            mean_citations_per_answer=0.0,
            hallucinated_marker_rate=0.0,
            hallucinated_marker_count=0,
            emitted_marker_count=0,
        )

    emitted = sum(len(record.emitted_markers) for record in records)
    hallucinated = sum(len(hallucinated_markers(record)) for record in records)
    cited = sum(1 for record in records if record.valid_markers)
    valid_total = sum(len(record.valid_markers) for record in records)

    return CitationMetrics(
        answers_with_citations=cited / len(records),
        mean_citations_per_answer=valid_total / len(records),
        hallucinated_marker_rate=hallucinated / emitted if emitted else 0.0,
        hallucinated_marker_count=hallucinated,
        emitted_marker_count=emitted,
    )
