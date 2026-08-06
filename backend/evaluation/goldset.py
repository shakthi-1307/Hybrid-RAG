"""Reading and writing the gold set and its unreviewed candidates."""

from __future__ import annotations

from pathlib import Path

from evaluation.config import CANDIDATES_PATH, GOLDSET_PATH, GOLDSET_VERSION
from evaluation.schema import GoldQuestion, GoldSet


def _write(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")


def save_candidates(candidates: GoldSet) -> Path:
    _write(CANDIDATES_PATH, candidates.model_dump_json(indent=2))
    return CANDIDATES_PATH


def load_candidates() -> GoldSet:
    if not CANDIDATES_PATH.exists():
        raise FileNotFoundError(
            f"No drafted questions at {CANDIDATES_PATH}. Run 'generate' first."
        )
    return GoldSet.model_validate_json(CANDIDATES_PATH.read_text(encoding="utf-8"))


def save_goldset(owner_email: str, questions: list[GoldQuestion]) -> Path:
    goldset = GoldSet(
        version=GOLDSET_VERSION, owner_email=owner_email, questions=questions
    )
    _write(GOLDSET_PATH, goldset.model_dump_json(indent=2))
    return GOLDSET_PATH


def load_goldset() -> GoldSet:
    if not GOLDSET_PATH.exists():
        raise FileNotFoundError(
            f"No gold set at {GOLDSET_PATH}. Run 'generate' then 'review' first."
        )
    return GoldSet.model_validate_json(GOLDSET_PATH.read_text(encoding="utf-8"))
