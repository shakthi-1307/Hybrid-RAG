"""Data shapes for the gold set and the benchmark report."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class GoldQuestion(BaseModel):
    """One benchmark item: a question and the section that answers it.

    ``reference_answer`` is optional. Supplying it unlocks the RAGAS metrics
    that need ground truth (context recall); without it the harness runs the
    reference-free subset instead of silently reporting nothing.
    """

    question: str
    expected_section: str
    document_title: str
    source_chunk_id: str
    reference_answer: str = ""
    note: str = ""


class GoldSet(BaseModel):
    version: int
    owner_email: str
    questions: list[GoldQuestion] = Field(default_factory=list)


class StageTimings(BaseModel):
    vector_ms: float = 0.0
    lexical_ms: float = 0.0
    fusion_ms: float = 0.0
    hydrate_ms: float = 0.0
    rerank_ms: float = 0.0

    def total_ms(self) -> float:
        return (
            self.vector_ms
            + self.lexical_ms
            + self.fusion_ms
            + self.hydrate_ms
            + self.rerank_ms
        )


class QuestionOutcome(BaseModel):
    question: str
    expected_section: str
    retrieved_sections: list[str]
    hit: bool
    rank: int | None
    reciprocal_rank: float
    ndcg: float
    timings: StageTimings


class ConfigurationResult(BaseModel):
    name: str
    description: str
    hit_rate: float
    hit_rate_ci_low: float
    hit_rate_ci_high: float
    mrr: float
    ndcg: float
    p50_ms: float
    p95_ms: float
    mean_stage_ms: dict[str, float]
    outcomes: list[QuestionOutcome]


class EvaluationReport(BaseModel):
    generated_at: datetime
    top_k: int
    question_count: int
    embedding_model: str
    reranker_model: str
    configurations: list[ConfigurationResult]


class AnswerRecord(BaseModel):
    """One generated answer with the context it was allowed to use."""

    question: str
    answer: str
    contexts: list[str]
    context_sections: list[str]
    reference_answer: str = ""
    emitted_markers: list[int] = Field(default_factory=list)
    valid_markers: list[int] = Field(default_factory=list)


class CitationMetrics(BaseModel):
    """Measured directly, not by an LLM judge — so they are exact, not scored."""

    answers_with_citations: float
    mean_citations_per_answer: float
    hallucinated_marker_rate: float
    hallucinated_marker_count: int
    emitted_marker_count: int


class GenerationReport(BaseModel):
    generated_at: datetime
    question_count: int
    retrieval_configuration: str
    judge_model: str
    reference_answers_available: bool
    citation: CitationMetrics
    ragas: dict[str, float] = Field(default_factory=dict)
    records: list[AnswerRecord] = Field(default_factory=list)
