"""Retrieval metrics and the section-matching rule they depend on.

Pure functions only — no database, no models, no I/O — so every number in the
report can be unit-tested independently of the pipeline that produced it.
"""

from __future__ import annotations

import math
import re

from evaluation.config import WILSON_Z

_WHITESPACE_RE = re.compile(r"\s+")


def normalise(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text).strip().lower()


def matches_expected(expected: str, retrieved_section: str) -> bool:
    """Whether a retrieved heading path satisfies the expected section.

    Containment rather than equality: the gold set records a section name such
    as "Refunds" while retrieval returns the full path "Billing > Refunds".
    Requiring equality would score correct retrievals as misses.
    """
    return normalise(expected) in normalise(retrieved_section)


def first_relevant_rank(expected: str, retrieved_sections: list[str]) -> int | None:
    """1-based rank of the first matching section, or None if absent."""
    for position, section in enumerate(retrieved_sections, start=1):
        if matches_expected(expected, section):
            return position
    return None


def reciprocal_rank(rank: int | None) -> float:
    return 0.0 if rank is None else 1.0 / rank


def ndcg_at_k(rank: int | None, k: int) -> float:
    """nDCG with a single relevant item and binary relevance.

    The ideal ranking puts it first, so IDCG is 1 and nDCG reduces to the
    discount alone. Unlike hit rate this distinguishes rank 1 from rank 6,
    which is exactly what a reranker is supposed to improve.
    """
    if rank is None or rank > k:
        return 0.0
    return 1.0 / math.log2(rank + 1)


def wilson_interval(successes: int, total: int) -> tuple[float, float]:
    """95% Wilson score interval for a proportion.

    Reported alongside every hit rate because a 30-question benchmark carries
    an interval wide enough to change how the result should be read.
    """
    if total == 0:
        return 0.0, 0.0

    proportion = successes / total
    z_squared = WILSON_Z**2
    denominator = 1 + z_squared / total
    centre = (proportion + z_squared / (2 * total)) / denominator
    margin = (
        WILSON_Z
        * math.sqrt(proportion * (1 - proportion) / total + z_squared / (4 * total**2))
    ) / denominator
    return max(0.0, centre - margin), min(1.0, centre + margin)


def percentile(values: list[float], fraction: float) -> float:
    """Nearest-rank percentile. Small samples do not justify interpolation."""
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(fraction * len(ordered)) - 1)
    return ordered[index]
