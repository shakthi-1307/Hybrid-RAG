"""LangGraph node functions. Each one is a pure state transition."""

from __future__ import annotations

import logging

from app.config import settings
from app.generation.citations import build_citations, extract_citation_markers
from app.generation.llm import groq_client
from app.generation.prompt import SYSTEM_PROMPT, build_user_prompt
from app.graph.state import RAGState
from app.retrieval import hybrid_retriever

logger = logging.getLogger(__name__)

GENERATE_BRANCH = "generate"
FALLBACK_BRANCH = "fallback"


def retrieve_node(state: RAGState) -> RAGState:
    scored = hybrid_retriever.retrieve(
        session=state["db"],
        query=state["question"],
        top_k=settings.TOP_K,
        owner_id=state["owner_id"],
    )
    logger.info("Retrieved %d chunks for query", len(scored))
    return {"retrieved": scored}


def route_after_retrieve(state: RAGState) -> str:
    return GENERATE_BRANCH if state["retrieved"] else FALLBACK_BRANCH


def generate_node(state: RAGState) -> RAGState:
    chunks = [scored.chunk for scored in state["retrieved"]]
    answer = groq_client.complete(
        SYSTEM_PROMPT,
        build_user_prompt(state["question"], chunks, state["history"]),
    )
    return {"answer": answer, "grounded": True}


def fallback_node(state: RAGState) -> RAGState:
    logger.info("No context retrieved for question: %s", state["question"][:120])
    return {
        "answer": settings.NO_CONTEXT_ANSWER,
        "grounded": False,
        "citations": [],
    }


def cite_node(state: RAGState) -> RAGState:
    chunks = [scored.chunk for scored in state["retrieved"]]
    markers = extract_citation_markers(state["answer"])
    return {"citations": build_citations(markers, chunks)}
