"""Runs the full answer pipeline over the gold set to produce eval records.

Composed from the same primitives as the request path rather than calling the
LangGraph pipeline, for the same reason ``configurations`` is: the harness needs
the retrieved contexts alongside the answer, and needs to be able to swap the
retrieval configuration underneath a fixed generator.
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy.orm import Session

from app.config import settings
from app.generation.citations import build_citations, extract_citation_markers
from app.generation.llm import groq_client
from app.generation.prompt import (
    SYSTEM_PROMPT,
    build_user_prompt,
    format_source_label,
)
from app.retrieval.hydration import hydrate_chunks
from evaluation.configurations import run_hybrid_reranked
from evaluation.schema import AnswerRecord, GoldSet

logger = logging.getLogger(__name__)

RETRIEVAL_CONFIGURATION = "hybrid_reranked"
"""Answers are generated over the best retrieval configuration; the retrieval
benchmark is what compares the alternatives."""


def generate_answers(
    session: Session, goldset: GoldSet, owner_id: UUID
) -> list[AnswerRecord]:
    records: list[AnswerRecord] = []

    for index, question in enumerate(goldset.questions, start=1):
        output = run_hybrid_reranked(session, question.question, owner_id, settings.TOP_K)
        chunks = hydrate_chunks(session, owner_id, output.chunk_ids)
        if not chunks:
            logger.warning("No context retrieved for: %s", question.question)
            continue

        try:
            answer = groq_client.complete(
                SYSTEM_PROMPT, build_user_prompt(question.question, chunks, [])
            )
        except Exception:  # noqa: BLE001 - one failure must not end the run
            logger.exception("Generation failed for: %s", question.question)
            continue

        emitted = extract_citation_markers(answer)
        citations = build_citations(emitted, chunks)

        records.append(
            AnswerRecord(
                question=question.question,
                answer=answer,
                contexts=[chunk.text for chunk in chunks],
                context_sections=[format_source_label(chunk) for chunk in chunks],
                reference_answer=question.reference_answer,
                emitted_markers=emitted,
                valid_markers=[citation.marker for citation in citations],
            )
        )
        logger.info("Answered %d/%d", index, len(goldset.questions))

    return records
