"""Constants for the evaluation harness.

Separate from ``app.config`` on purpose: these describe how the benchmark is
run, not how the service behaves. Nothing here is read by request-path code.
"""

from __future__ import annotations

import os
from pathlib import Path

# Defaults to the persistent volume so gold sets and results survive a rebuild.
EVAL_DIR = Path(os.environ.get("EVAL_DIR", "/data/evaluation"))
CANDIDATES_PATH = EVAL_DIR / "candidates.json"
GOLDSET_PATH = EVAL_DIR / "goldset.json"
RESULTS_DIR = EVAL_DIR / "results"

GOLDSET_VERSION = 1

# --- question drafting -------------------------------------------------------
DRAFT_CHUNK_SAMPLE_SIZE = 25
DRAFT_QUESTIONS_PER_CHUNK = 2
# Very short chunks (headers, captions) make degenerate questions.
DRAFT_MIN_CHUNK_CHARS = 300
DRAFT_SNIPPET_CHARS = 1200

# --- statistics --------------------------------------------------------------
WILSON_Z = 1.96  # 95% confidence
P50 = 0.50
P95 = 0.95

# --- RAGAS -------------------------------------------------------------------
# The judge is deliberately a different, larger model than the one under test
# would ideally be — a model grading its own output is a weak evaluator.
RAGAS_JUDGE_MODEL = os.environ.get("RAGAS_JUDGE_MODEL", "openai/gpt-oss-120b")
RAGAS_JUDGE_TEMPERATURE = 0.0
RAGAS_TIMEOUT_SECONDS = 180
# RAGAS defaults to 16 workers, which trips Groq's rate limit immediately.
RAGAS_MAX_WORKERS = 4

# --- run ---------------------------------------------------------------------
# The first query pays for lazy model loading; excluded so latency reflects
# steady state rather than a one-off download and initialisation.
LATENCY_WARMUP_QUERIES = 2
