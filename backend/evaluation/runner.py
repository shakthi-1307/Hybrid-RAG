"""Executes every configuration over the gold set and aggregates the results."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.config import settings
from evaluation.config import LATENCY_WARMUP_QUERIES, P50, P95
from evaluation.configurations import CONFIGURATIONS, ConfigurationRunner
from evaluation.corpus import sections_for_chunk_ids
from evaluation.metrics import (
    first_relevant_rank,
    ndcg_at_k,
    percentile,
    reciprocal_rank,
    wilson_interval,
)
from evaluation.schema import (
    ConfigurationResult,
    EvaluationReport,
    GoldSet,
    QuestionOutcome,
    StageTimings,
)

logger = logging.getLogger(__name__)

STAGE_NAMES = ("vector_ms", "lexical_ms", "fusion_ms", "hydrate_ms", "rerank_ms")


def _warm_up(
    session: Session, runner: ConfigurationRunner, goldset: GoldSet, owner_id: UUID
) -> None:
    """Absorb lazy model loading so it is not billed to the first question."""
    for question in goldset.questions[:LATENCY_WARMUP_QUERIES]:
        runner(session, question.question, owner_id, settings.TOP_K)


def _mean_stage_times(timings: list[StageTimings]) -> dict[str, float]:
    if not timings:
        return {stage: 0.0 for stage in STAGE_NAMES}
    return {
        stage: sum(getattr(t, stage) for t in timings) / len(timings)
        for stage in STAGE_NAMES
    }


def _evaluate_configuration(
    session: Session,
    name: str,
    description: str,
    runner: ConfigurationRunner,
    goldset: GoldSet,
    owner_id: UUID,
) -> ConfigurationResult:
    logger.info("Running configuration %s", name)
    _warm_up(session, runner, goldset, owner_id)

    outcomes: list[QuestionOutcome] = []
    for question in goldset.questions:
        output = runner(session, question.question, owner_id, settings.TOP_K)

        # Section lookup happens after the timed region: it exists to score the
        # ranking, not to serve it, and must not inflate any configuration.
        sections = sections_for_chunk_ids(session, owner_id, output.chunk_ids)
        retrieved = [sections.get(chunk_id, "") for chunk_id in output.chunk_ids]

        rank = first_relevant_rank(question.expected_section, retrieved)
        outcomes.append(
            QuestionOutcome(
                question=question.question,
                expected_section=question.expected_section,
                retrieved_sections=retrieved,
                hit=rank is not None,
                rank=rank,
                reciprocal_rank=reciprocal_rank(rank),
                ndcg=ndcg_at_k(rank, settings.TOP_K),
                timings=output.timings,
            )
        )

    total = len(outcomes)
    hits = sum(outcome.hit for outcome in outcomes)
    latencies = [outcome.timings.total_ms() for outcome in outcomes]
    low, high = wilson_interval(hits, total)

    return ConfigurationResult(
        name=name,
        description=description,
        hit_rate=hits / total if total else 0.0,
        hit_rate_ci_low=low,
        hit_rate_ci_high=high,
        mrr=sum(o.reciprocal_rank for o in outcomes) / total if total else 0.0,
        ndcg=sum(o.ndcg for o in outcomes) / total if total else 0.0,
        p50_ms=percentile(latencies, P50),
        p95_ms=percentile(latencies, P95),
        mean_stage_ms=_mean_stage_times([o.timings for o in outcomes]),
        outcomes=outcomes,
    )


def run_evaluation(
    session: Session, goldset: GoldSet, owner_id: UUID
) -> EvaluationReport:
    if not goldset.questions:
        raise RuntimeError("The gold set is empty; nothing to evaluate.")

    # No index build step. Both indexes live in Postgres and are maintained as
    # rows are written, so this CLI sees exactly what the API sees — which was
    # not true when the lexical index was per-process memory and this harness
    # had to rebuild it before every run to avoid scoring zero.

    return EvaluationReport(
        generated_at=datetime.now(UTC),
        top_k=settings.TOP_K,
        question_count=len(goldset.questions),
        embedding_model=settings.EMBEDDING_MODEL_NAME,
        reranker_model=settings.RERANKER_MODEL_NAME,
        configurations=[
            _evaluate_configuration(session, name, description, runner, goldset, owner_id)
            for name, description, runner in CONFIGURATIONS
        ],
    )
