from __future__ import annotations

from app.retrieval.fusion import LEXICAL_SOURCE, VECTOR_SOURCE, reciprocal_rank_fusion

K = 60
EQUAL_WEIGHTS = {VECTOR_SOURCE: 1.0, LEXICAL_SOURCE: 1.0}


def test_agreement_between_sources_outranks_a_single_top_hit():
    fused = reciprocal_rank_fusion(
        ranked_lists={
            VECTOR_SOURCE: ["solo", "agreed"],
            LEXICAL_SOURCE: ["other", "agreed"],
        },
        weights=EQUAL_WEIGHTS,
        k=K,
    )

    assert fused[0].chunk_id == "agreed"
    assert fused[0].ranks == {VECTOR_SOURCE: 2, LEXICAL_SOURCE: 2}


def test_score_matches_the_rrf_formula():
    fused = reciprocal_rank_fusion(
        ranked_lists={VECTOR_SOURCE: ["a"], LEXICAL_SOURCE: ["a"]},
        weights={VECTOR_SOURCE: 1.0, LEXICAL_SOURCE: 0.5},
        k=K,
    )

    assert fused[0].score == 1.0 / (K + 1) + 0.5 / (K + 1)


def test_weights_can_favour_one_source():
    fused = reciprocal_rank_fusion(
        ranked_lists={VECTOR_SOURCE: ["dense"], LEXICAL_SOURCE: ["lexical"]},
        weights={VECTOR_SOURCE: 2.0, LEXICAL_SOURCE: 1.0},
        k=K,
    )

    assert fused[0].chunk_id == "dense"


def test_empty_lists_produce_no_results():
    assert (
        reciprocal_rank_fusion(
            ranked_lists={VECTOR_SOURCE: [], LEXICAL_SOURCE: []},
            weights=EQUAL_WEIGHTS,
            k=K,
        )
        == []
    )


def test_ordering_is_deterministic_for_tied_scores():
    lists = {VECTOR_SOURCE: ["b", "a"], LEXICAL_SOURCE: ["a", "b"]}
    first = reciprocal_rank_fusion(lists, EQUAL_WEIGHTS, K)
    second = reciprocal_rank_fusion(lists, EQUAL_WEIGHTS, K)

    assert [r.chunk_id for r in first] == [r.chunk_id for r in second]
