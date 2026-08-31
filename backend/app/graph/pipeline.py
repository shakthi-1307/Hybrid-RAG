"""The compiled LangGraph query pipeline.

retrieve ─┬─(hits)──► generate ──► cite ──► END
          └─(none)──► fallback ─────────────► END
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from langgraph.graph import END, StateGraph
from sqlalchemy.orm import Session

from app.config import settings
from app.generation.citations import build_citations, extract_citation_markers
from app.generation.llm import groq_client
from app.generation.prompt import SYSTEM_PROMPT, build_user_prompt
from app.graph.nodes import (
    FALLBACK_BRANCH,
    GENERATE_BRANCH,
    cite_node,
    fallback_node,
    generate_node,
    retrieve_node,
    route_after_retrieve,
)
from app.graph.state import RAGState
from app.schemas.chat import Citation
from app.schemas.retrieval import RetrievedChunk


@dataclass(frozen=True)
class RAGResult:
    answer: str
    citations: list[Citation]
    grounded: bool


@dataclass
class StreamedAnswer:
    """Accumulates a streamed answer so it can be cited once complete.

    Citation validation is not incremental. A marker is only trustworthy once
    the full text exists, because the model may still be writing the number —
    "[1" is not yet "[12]". So tokens stream immediately for latency, and the
    validated citation list follows as a final event. The caller reconciles
    them at the end.
    """

    text: str = ""
    citations: list[Citation] = field(default_factory=list)
    grounded: bool = False
    chunks: list[RetrievedChunk] = field(default_factory=list)


def build_graph() -> Any:
    graph = StateGraph(RAGState)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node(GENERATE_BRANCH, generate_node)
    graph.add_node("cite", cite_node)
    graph.add_node(FALLBACK_BRANCH, fallback_node)

    graph.set_entry_point("retrieve")
    graph.add_conditional_edges(
        "retrieve",
        route_after_retrieve,
        {GENERATE_BRANCH: GENERATE_BRANCH, FALLBACK_BRANCH: FALLBACK_BRANCH},
    )
    graph.add_edge(GENERATE_BRANCH, "cite")
    graph.add_edge("cite", END)
    graph.add_edge(FALLBACK_BRANCH, END)
    return graph.compile()


rag_graph = build_graph()


def answer_question(
    session: Session,
    owner_id: UUID,
    question: str,
    history: list[tuple[str, str]],
) -> RAGResult:
    final_state: RAGState = rag_graph.invoke(
        {
            "db": session,
            "owner_id": owner_id,
            "question": question,
            "history": history,
        }
    )
    return RAGResult(
        answer=final_state["answer"],
        citations=final_state.get("citations", []),
        grounded=final_state["grounded"],
    )


def stream_answer(
    session: Session,
    owner_id: UUID,
    question: str,
    history: list[tuple[str, str]],
    result: StreamedAnswer,
) -> Iterator[str]:
    """Retrieve, then yield answer tokens, filling ``result`` as it goes.

    This deliberately does not run through the compiled graph. LangGraph nodes
    return state; they do not yield, so token-level streaming would mean
    pushing tokens into a queue from inside a node and draining it outside —
    machinery that obscures a sequence which is, once retrieval has branched,
    entirely linear. The retrieval and citation steps still call the same
    functions the graph nodes call, so the two paths cannot diverge in
    behaviour.

    ``result`` is an out-parameter because a generator's return value is not
    reachable through normal iteration, and the caller needs the citations
    after the last token.
    """
    state: RAGState = {
        "db": session,
        "owner_id": owner_id,
        "question": question,
        "history": history,
    }
    retrieved = retrieve_node(state)["retrieved"]
    result.chunks = [scored.chunk for scored in retrieved]

    if not retrieved:
        result.text = settings.NO_CONTEXT_ANSWER
        result.grounded = False
        result.citations = []
        yield settings.NO_CONTEXT_ANSWER
        return

    result.grounded = True
    pieces: list[str] = []
    for piece in groq_client.stream(
        SYSTEM_PROMPT,
        build_user_prompt(question, result.chunks, history),
    ):
        pieces.append(piece)
        yield piece

    result.text = "".join(pieces).strip()
    result.citations = build_citations(
        extract_citation_markers(result.text), result.chunks
    )
