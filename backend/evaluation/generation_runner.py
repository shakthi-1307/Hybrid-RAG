"""Orchestrates the generation-quality benchmark.

Two independent views of the same answers: exact citation counts, and
LLM-judged RAGAS scores. They are reported side by side on purpose — if the
judge says an answer is faithful while the citation counter says the model
invented a source number, that disagreement is the interesting result.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.retrieval.index_builder import refresh_bm25_index
from evaluation.answers import RETRIEVAL_CONFIGURATION, generate_answers
from evaluation.citation_metrics import summarise
from evaluation.config import RAGAS_JUDGE_MODEL
from evaluation.ragas_adapter import evaluate_generation
from evaluation.schema import GenerationReport, GoldSet

logger = logging.getLogger(__name__)


def run_generation_evaluation(
    session: Session, goldset: GoldSet, owner_id: UUID
) -> GenerationReport:
    if not goldset.questions:
        raise RuntimeError("The gold set is empty; nothing to evaluate.")

    # This CLI is a separate process from the API, so the in-memory lexical
    # index has to be built here or hybrid retrieval silently returns nothing.
    refresh_bm25_index(session)

    records = generate_answers(session, goldset, owner_id)
    if not records:
        raise RuntimeError("No answers were produced; check the Groq API key.")

    return GenerationReport(
        generated_at=datetime.now(timezone.utc),
        question_count=len(records),
        retrieval_configuration=RETRIEVAL_CONFIGURATION,
        judge_model=RAGAS_JUDGE_MODEL,
        reference_answers_available=all(r.reference_answer for r in records),
        citation=summarise(records),
        ragas=evaluate_generation(records),
        records=records,
    )
