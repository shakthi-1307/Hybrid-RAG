# Resume content — Hybrid RAG platform

Targeted at **AI/ML Engineer** and **Full-Stack Engineer** roles, new-grad level.

> **Read this first.** Every number in the bullets below is verifiable from the
> repository — module counts, test counts, and parameters you actually tuned.
> None of them are invented.
>
> What is *missing* is measured impact: latency, throughput, and retrieval
> quality. Those are the numbers recruiters and interviewers weigh most, and
> fabricating them is the fastest way to fail a technical screen — an
> interviewer who asks "how did you measure that?" will get an answer you
> don't have. Section 6 shows how to generate real ones in about an hour.
> The single highest-value number is **hit-rate of hybrid vs. vector-only**,
> because it justifies the whole architecture.

---

## 1. Project title

Pick one. The first is strongest — it names the technique, not the category.

- **Hybrid Retrieval RAG Platform — Multi-Tenant Document QA with Verifiable Citations**
- **Citation-Grounded RAG System (BM25 + Dense Retrieval, Reciprocal Rank Fusion)**
- **Multi-Tenant Document Intelligence Platform**

Avoid "RAG Chatbot." It reads as tutorial-follower and is the single most
common project title in the pile.

---

## 2. Tech stack line

Place immediately under the title. This is what the ATS parses first.

> **Python, FastAPI, React, PostgreSQL, ChromaDB, LangGraph, SQLAlchemy,
> Alembic, Docker, nginx, pytest, sentence-transformers, Hugging Face, Groq
> (Llama 3.3 70B), BM25, JWT, bcrypt**

---

## 3. Primary version — 6 bullets

Lead bullet establishes scope. Bullets 2–4 are the technical differentiators.
Bullets 5–6 signal production maturity, which is what separates this from a
notebook.

- Built a **multi-tenant Retrieval-Augmented Generation (RAG)** platform over
  user-uploaded PDF/Markdown corpora — **46 backend modules, 58 unit tests, 2
  schema migrations**, containerised with Docker Compose and served through an
  nginx reverse proxy.
- Engineered **hybrid retrieval** fusing **dense vector search**
  (BAAI/bge-small-en-v1.5, 384-dim, cosine) with **BM25 lexical ranking** via
  **Reciprocal Rank Fusion** (k=60, weighted 1.0/0.8), reranking **40+40
  candidates** to a top-6 context window and recovering exact-match identifiers
  that pure embedding similarity misses.
- Designed **structure-aware chunking** that reconstructs PDF heading hierarchy
  from font-size ranking and embedded TOC metadata, packing **512-token chunks
  with 64-token overlap** that never cross section boundaries — enabling
  citations resolved to **document → section → page** instead of opaque chunk IDs.
- Implemented a **LangGraph** state machine with conditional branching for
  retrieve → generate → cite, **validating every `[n]` citation the LLM emits
  against the context actually supplied** and discarding hallucinated
  references before they reach the user.
- Enforced tenant isolation across **4 independent layers** — vector-store
  metadata filtering applied pre-ANN-cut, lexical filtering pre-truncation,
  owner-scoped SQL predicates, and re-verification at hydration — so no single
  defect can expose another user's documents.
- Hardened for deployment: **bcrypt (cost 12) + JWT httpOnly-cookie auth**,
  sliding-window rate limiting, per-user quotas (**100 documents / 500 MB**),
  fail-closed startup validation rejecting weak secrets, and **60+ tunable
  parameters centralised in a single config module**.

---

## 4. Condensed — 3 bullets

For when the project is one of several and space is tight.

- Built a **multi-tenant RAG platform** (FastAPI, React, PostgreSQL, ChromaDB,
  Docker) delivering citation-grounded answers over user-uploaded PDF/Markdown
  corpora — **46 modules, 58 tests**.
- Engineered **hybrid retrieval** fusing **BM25** with **384-dim dense
  embeddings** via **Reciprocal Rank Fusion** (k=60), plus **structure-aware
  chunking** that preserves heading hierarchy so every answer cites
  **document → section → page**.
- Validated LLM-emitted citations against supplied context inside a
  **LangGraph** pipeline, and enforced per-tenant isolation across **4
  independent layers** spanning the vector store, lexical index, and SQL layer.

---

## 5. One-liner

For a skills summary or LinkedIn headline.

> Multi-tenant RAG platform with hybrid BM25 + dense retrieval fused via
> Reciprocal Rank Fusion, structure-aware chunking, and section-level verified
> citations — FastAPI, React, PostgreSQL, ChromaDB, LangGraph, Docker.

---

## 6. Numbers to measure — do this before you send it

Each takes minutes and turns a structural bullet into an impact bullet.

### (a) Retrieval quality — highest value, do this one first

This is the number that justifies your architecture. Without it, "hybrid
retrieval" is a design choice; with it, it's a result.

1. Ingest 3–5 documents you know well.
2. Write **20–30 questions** with the heading you'd expect the answer under.
3. For each question, run retrieval three ways — vector-only, BM25-only,
   hybrid — and record whether the correct section appears in the top 6.

```python
# backend/scripts/eval_retrieval.py  (throwaway; do not commit as app code)
from app.retrieval import vector_search
from app.retrieval.bm25_search import bm25_index
from app.retrieval.fusion import BM25_SOURCE, VECTOR_SOURCE, reciprocal_rank_fusion
from app.config import settings

# GOLD = [("what is the refund window?", "Billing > Refunds"), ...]
def hit_rate(gold, mode, owner_id, session):
    hits = 0
    for question, expected_section in gold:
        vec = [c for c, _ in vector_search.search(question, 40, owner_id)]
        lex = [c for c, _ in bm25_index.search(question, 40, owner_id)]
        if mode == "vector":
            ranked = vec[: settings.TOP_K]
        elif mode == "bm25":
            ranked = lex[: settings.TOP_K]
        else:
            ranked = [
                r.chunk_id
                for r in reciprocal_rank_fusion(
                    {VECTOR_SOURCE: vec, BM25_SOURCE: lex},
                    {VECTOR_SOURCE: settings.RRF_VECTOR_WEIGHT,
                     BM25_SOURCE: settings.RRF_BM25_WEIGHT},
                    settings.RRF_K,
                )[: settings.TOP_K]
            ]
        # resolve ranked chunk ids -> heading_path, compare to expected_section
        hits += int(any(expected_section in s for s in sections_of(ranked, session)))
    return hits / len(gold)
```

Resulting bullet:

> Raised top-6 retrieval hit-rate from **__% (vector-only)** to **__% (hybrid
> RRF)** on a **30-question** benchmark, a **__ percentage-point** gain
> concentrated on queries containing exact identifiers.

If hybrid *doesn't* beat vector-only on your corpus, that is still a strong
bullet — say so and explain the corpus characteristic that caused it. Being
able to describe a negative result is rare in a new-grad portfolio and reads as
genuine engineering rather than a copied tutorial.

### (b) Query latency

```bash
# after signing in, with the session cookie saved to cookies.txt
for i in $(seq 1 20); do
  curl -s -o /dev/null -w "%{time_total}\n" -b cookies.txt \
    -H 'Content-Type: application/json' \
    -d '{"question":"your question"}' \
    http://localhost:5173/api/v1/chat/sessions/<id>/query
done | sort -n | awk '{a[NR]=$1} END {print "p50",a[int(NR*0.5)]; print "p95",a[int(NR*0.95)]}'
```

> Served grounded answers at **__ ms p50 / __ ms p95** end-to-end, with
> retrieval accounting for **__ ms** of that.

Break out retrieval separately — it's the part you control. Groq's generation
time isn't your engineering.

### (c) Ingestion throughput

Already in your logs: `Ingested <file> into N chunks`. Time a 100-page PDF.

> Ingested a **__-page PDF into __ chunks in __ s** (**__ pages/s**) on CPU-only
> inference.

### (d) Corpus scale

From `GET /api/v1/health` → `vector_count`, `bm25_documents`.

> Indexed **__ chunks across __ documents**, retrieved in **__ ms**.

---

## 7. ATS keyword bank

ATS matching is largely literal. If a posting says "vector database" and your
resume only says "ChromaDB," some parsers score it zero — include both the
generic term and the specific tool.

**Core — must appear**
`Retrieval-Augmented Generation (RAG)` · `Large Language Models (LLM)` ·
`vector database` · `semantic search` · `embeddings` · `information retrieval` ·
`natural language processing (NLP)` · `hybrid search` · `BM25` ·
`Reciprocal Rank Fusion` · `re-ranking` · `prompt engineering`

**Tools**
`Python` · `FastAPI` · `React` · `PostgreSQL` · `ChromaDB` · `LangGraph` ·
`SQLAlchemy` · `Alembic` · `Docker` · `Docker Compose` · `nginx` · `pytest` ·
`sentence-transformers` · `Hugging Face` · `PyTorch` · `Groq` · `Llama 3.3` ·
`REST API` · `JWT` · `bcrypt` · `Vite`

**Engineering signals**
`multi-tenant architecture` · `database schema design` · `schema migrations` ·
`API design` · `unit testing` · `containerisation` · `background job
processing` · `authentication and authorisation` · `rate limiting` ·
`observability`

**Do not claim** — not in this project: LangChain (only LangGraph),
Kubernetes, CI/CD, AWS/GCP, Redis, Kafka, fine-tuning, RAGAS. Every one of
these is a question you'd have to walk back in an interview.

---

## 8. Why this isn't another generic RAG project

Interview talking points. Most portfolio RAG projects are: load PDF → split on
character count → embed → cosine top-k → stuff into prompt. Yours differs at
four specific points, and naming them is what makes you memorable.

| Generic project | This project |
|---|---|
| Fixed-size character splitting | Structure-aware chunking; chunks never cross a heading boundary, so a citation maps to a real section |
| Cosine similarity only | BM25 + dense, fused with RRF — because cosine and BM25 scores are unnormalisable against each other, only their *ranks* are comparable |
| "Source: doc.pdf" | `document → section → page`, and hallucinated `[n]` markers are dropped before render |
| Single user, no auth | 4-layer tenant isolation; filters applied *before* the top-N cut, not after |
| Linear script | LangGraph state machine with a conditional no-context branch |
| Magic numbers scattered inline | 60+ parameters in one config module; no tunable literal anywhere else |

**The strongest single thing you can say in an interview:** *"Filtering after
the nearest-neighbour cut would return the filtered remains of a global top-N
rather than the true top-N for that user — so the metadata filter is applied
pre-cut in Chroma, and the lexical filter pre-truncation in BM25."* That
sentence demonstrates you understand what an ANN index actually does, which
almost nobody at new-grad level can articulate.

**Second strongest:** why RRF instead of normalising and weighting scores.
Cosine similarity is bounded, BM25 is unbounded and corpus-dependent; any
score-level blend needs recalibration per corpus, while rank-level fusion
doesn't.

---

## 9. Placement on the page

- **Projects** section, first entry — it's your strongest artifact.
- Title, then stack line, then bullets. Live demo or GitHub link on the title line.
- If you have a GitHub link, pin the repo and make sure the README renders —
  recruiters click through, and yours documents architecture and trade-offs
  rather than just install steps. That README is doing real work for you.
- Mirror the exact phrasing of each job posting: if it says "vector search,"
  use "vector search" in that application even though your README says "dense
  retrieval."
