"""The compiled LangGraph query pipeline.

    retrieve ─┬─(hits)──► generate ──► cite ──► END
              └─(none)──► fallback ─────────────► END
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from langgraph.graph import END, StateGraph
from sqlalchemy.orm import Session

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


@dataclass(frozen=True)
class RAGResult:
    answer: str
    citations: list[Citation]
    grounded: bool


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
