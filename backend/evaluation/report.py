"""Renders a benchmark report as JSON and as a Markdown table."""

from __future__ import annotations

from pathlib import Path

from evaluation.config import RESULTS_DIR
from evaluation.schema import (
    ConfigurationResult,
    EvaluationReport,
    GenerationReport,
)

BASELINE_CONFIGURATION = "vector_only"
"""Deltas are quoted against dense-only retrieval, because that is what a
typical RAG implementation ships and therefore the comparison worth making."""


def _percent(value: float) -> str:
    return f"{value * 100:.1f}%"


def _delta(result: ConfigurationResult, baseline: ConfigurationResult) -> str:
    if result.name == baseline.name:
        return "baseline"
    points = (result.hit_rate - baseline.hit_rate) * 100
    return f"{points:+.1f} pp"


def _write(name: str, payload: str) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / name
    path.write_text(payload, encoding="utf-8")
    return path


def write_json(report: EvaluationReport) -> Path:
    stamp = report.generated_at.strftime("%Y%m%dT%H%M%SZ")
    return _write(f"retrieval-{stamp}.json", report.model_dump_json(indent=2))


def render_markdown(report: EvaluationReport) -> str:
    baseline = next(
        (c for c in report.configurations if c.name == BASELINE_CONFIGURATION),
        report.configurations[0],
    )

    lines = [
        "## Retrieval benchmark",
        "",
        f"- Questions: **{report.question_count}**  ",
        f"- Top-k: **{report.top_k}**  ",
        f"- Embeddings: `{report.embedding_model}`  ",
        f"- Reranker: `{report.reranker_model}`  ",
        f"- Run: {report.generated_at.isoformat()}",
        "",
        "| Configuration | Hit@k | 95% CI | MRR | nDCG | p50 | p95 | vs dense |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]

    for result in report.configurations:
        lines.append(
            f"| {result.description} "
            f"| **{_percent(result.hit_rate)}** "
            f"| {_percent(result.hit_rate_ci_low)}–{_percent(result.hit_rate_ci_high)} "
            f"| {result.mrr:.3f} "
            f"| {result.ndcg:.3f} "
            f"| {result.p50_ms:.0f} ms "
            f"| {result.p95_ms:.0f} ms "
            f"| {_delta(result, baseline)} |"
        )

    lines += [
        "",
        "### Mean latency by stage (ms)",
        "",
        "| Configuration | vector | lexical | fusion | hydrate | rerank |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for result in report.configurations:
        stages = result.mean_stage_ms
        lines.append(
            f"| {result.description} "
            f"| {stages['vector_ms']:.1f} "
            f"| {stages['lexical_ms']:.1f} "
            f"| {stages['fusion_ms']:.1f} "
            f"| {stages['hydrate_ms']:.1f} "
            f"| {stages['rerank_ms']:.1f} |"
        )

    lines += [
        "",
        f"Confidence intervals are Wilson score at 95% over n={report.question_count}. "
        "Latency excludes answer generation, which is bounded by the LLM provider "
        "rather than by retrieval.",
    ]
    return "\n".join(lines)


def write_markdown(report: EvaluationReport) -> Path:
    stamp = report.generated_at.strftime("%Y%m%dT%H%M%SZ")
    return _write(f"retrieval-{stamp}.md", render_markdown(report))


def render_generation_markdown(report: GenerationReport) -> str:
    citation = report.citation
    lines = [
        "## Generation benchmark",
        "",
        f"- Answers scored: **{report.question_count}**  ",
        f"- Retrieval: `{report.retrieval_configuration}`  ",
        f"- Judge: `{report.judge_model}`  ",
        f"- Run: {report.generated_at.isoformat()}",
        "",
        "### Citation integrity (counted, not judged)",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        f"| Answers carrying a citation | "
        f"**{_percent(citation.answers_with_citations)}** |",
        f"| Mean citations per answer | {citation.mean_citations_per_answer:.2f} |",
        f"| Invalid markers caught and dropped | "
        f"**{_percent(citation.hallucinated_marker_rate)}** "
        f"({citation.hallucinated_marker_count} of "
        f"{citation.emitted_marker_count}) |",
        "",
    ]

    if report.ragas:
        lines += [
            "### RAGAS (LLM-judged)",
            "",
            "| Metric | Score |",
            "| --- | --- |",
        ]
        lines += [
            f"| {name.replace('_', ' ')} | {score:.3f} |"
            for name, score in sorted(report.ragas.items())
        ]
        lines.append("")

    if not report.reference_answers_available:
        lines.append(
            "Reference-free metrics only — add `reference_answer` to gold "
            "questions to enable context recall."
        )
    lines.append(
        "\nCitation figures are exact counts. RAGAS scores come from an LLM "
        "judge and carry its error; they compare configurations well and make "
        "poor absolute claims."
    )
    return "\n".join(lines)


def write_generation_json(report: GenerationReport) -> Path:
    stamp = report.generated_at.strftime("%Y%m%dT%H%M%SZ")
    return _write(f"generation-{stamp}.json", report.model_dump_json(indent=2))


def write_generation_markdown(report: GenerationReport) -> Path:
    stamp = report.generated_at.strftime("%Y%m%dT%H%M%SZ")
    return _write(f"generation-{stamp}.md", render_generation_markdown(report))
