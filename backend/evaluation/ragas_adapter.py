"""The RAGAS boundary.

Everything version-sensitive is confined to this file. RAGAS changes its public
API between minor releases more often than most libraries, so the rest of the
harness talks to it only through ``evaluate_generation`` and receives plain
floats back.

The judge is Groq rather than the RAGAS default of OpenAI, and the embeddings
are the same local BGE model used for retrieval — so evaluation needs no
additional API key and no second embedding space.
"""

from __future__ import annotations

import logging
from typing import Any

from app.config import settings
from evaluation.config import (
    RAGAS_JUDGE_MODEL,
    RAGAS_JUDGE_TEMPERATURE,
    RAGAS_MAX_WORKERS,
    RAGAS_TIMEOUT_SECONDS,
)
from evaluation.schema import AnswerRecord

logger = logging.getLogger(__name__)

INSTALL_HINT = (
    "RAGAS is not installed in this image. Rebuild with the evaluation extras:\n"
    "  docker compose build --build-arg INSTALL_EVAL=true api\n"
    "or install locally:\n"
    "  pip install -r requirements-eval.txt"
)


def _build_judge() -> Any:
    from langchain_groq import ChatGroq
    from ragas.llms import LangchainLLMWrapper

    return LangchainLLMWrapper(
        ChatGroq(
            model=RAGAS_JUDGE_MODEL,
            api_key=settings.GROQ_API_KEY,
            temperature=RAGAS_JUDGE_TEMPERATURE,
            timeout=RAGAS_TIMEOUT_SECONDS,
        )
    )


def _build_embeddings() -> Any:
    from langchain_huggingface import HuggingFaceEmbeddings
    from ragas.embeddings import LangchainEmbeddingsWrapper

    return LangchainEmbeddingsWrapper(
        HuggingFaceEmbeddings(
            model_name=settings.EMBEDDING_MODEL_NAME,
            model_kwargs={"device": settings.EMBEDDING_DEVICE},
        )
    )


def _select_metrics(with_reference: bool) -> list[Any]:
    """Reference-free metrics always; ground-truth metrics only when earned."""
    from ragas.metrics import (
        Faithfulness,
        LLMContextPrecisionWithoutReference,
        ResponseRelevancy,
    )

    metrics: list[Any] = [
        Faithfulness(),
        ResponseRelevancy(),
        LLMContextPrecisionWithoutReference(),
    ]
    if with_reference:
        from ragas.metrics import LLMContextRecall

        metrics.append(LLMContextRecall())
    return metrics


def evaluate_generation(records: list[AnswerRecord]) -> dict[str, float]:
    """Mean score per RAGAS metric. Returns {} if there is nothing to score."""
    if not records:
        return {}

    try:
        from ragas import EvaluationDataset, SingleTurnSample, evaluate
    except ImportError as exc:
        raise RuntimeError(INSTALL_HINT) from exc

    with_reference = all(record.reference_answer for record in records)
    metrics = _select_metrics(with_reference)

    dataset = EvaluationDataset(
        samples=[
            SingleTurnSample(
                user_input=record.question,
                response=record.answer,
                retrieved_contexts=record.contexts,
                reference=record.reference_answer or None,
            )
            for record in records
        ]
    )

    logger.info(
        "Scoring %d answers with %d RAGAS metrics (judge=%s)",
        len(records),
        len(metrics),
        RAGAS_JUDGE_MODEL,
    )
    result = evaluate(
        dataset=dataset,
        metrics=metrics,
        llm=_build_judge(),
        embeddings=_build_embeddings(),
        raise_exceptions=False,
        run_config=_run_config(),
    )

    # to_pandas() is the most stable public surface across RAGAS versions;
    # the internal score dictionaries have been renamed more than once.
    frame = result.to_pandas()
    return {
        metric.name: float(frame[metric.name].mean())
        for metric in metrics
        if metric.name in frame.columns
    }


def _run_config() -> Any:
    """Groq rate-limits aggressively; RAGAS defaults to far more concurrency."""
    from ragas.run_config import RunConfig

    return RunConfig(max_workers=RAGAS_MAX_WORKERS, timeout=RAGAS_TIMEOUT_SECONDS)
