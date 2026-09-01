# Hybrid RAG

Structure-aware ingestion + hybrid retrieval (lexical × dense, fused with
Reciprocal Rank Fusion) behind a LangGraph pipeline that returns answers with
verifiable citations down to the document section and page, streamed token by
token.

Multi-user: each account has its own private knowledge base and its own chat
history. Documents, chunks, vectors, and conversations are all owner-scoped.

- **Backend** — FastAPI, SQLAlchemy 2, Alembic
- **Auth** — bcrypt + JWT in an httpOnly cookie
- **Storage** — Postgres for everything: rows, vectors (`pgvector`), and the
  lexical index (`tsvector` + GIN). One store, one transaction, one backup.
- **Vectors** — pgvector HNSW, cosine, 384-dim
- **Lexical** — Postgres full-text search, `ts_rank_cd`, maintained per row
- **Embeddings** — `BAAI/bge-small-en-v1.5`, local, CPU
- **Generation** — Groq (`llama-3.3-70b-versatile`), streamed over SSE
- **Ingestion** — a separate worker process draining a Postgres job queue,
  with retries, heartbeats, and crash recovery
- **Observability** — JSON logs with a request id and user id on every record,
  plus a per-stage latency breakdown for each request
- **Frontend** — React 18 + Vite

---

## Architecture

### Phase 1 — Ingestion

```
POST /documents ──► file to disk ──► ingestion_jobs row ──► 202 Accepted
                                            │
                    (separate worker process claims it)
                                            │
        loader ──► chunker ──► metadata ──► embedder ──► Postgres
          │           │            │                        │
     (heading      (token-      (flat,            one transaction:
      hierarchy)    bounded,     versioned         chunks + vectors
                    overlapped)  schema)           + status = ready
```

The API never embeds anything. It writes the file, queues a job, and returns —
so an API restart mid-ingest cannot strand a document, and a large PDF cannot
starve request handling. See [The ingestion queue](#the-ingestion-queue).

| Stage       | File                                                      | Responsibility                                                                                                        |
| ----------- | --------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| Load        | `ingestion/loaders/pdf_loader.py`, `markdown_loader.py`   | Raw file → ordered `Section`s carrying a heading path                                                                 |
| Route       | `ingestion/loaders/registry.py`                           | Extension → loader; the only place formats are declared                                                               |
| Count       | `ingestion/tokenizer.py`                                  | Token counts from the _embedding model's own_ tokenizer                                                               |
| Chunk       | `ingestion/chunker.py`                                    | Greedy sentence packing to `CHUNK_TARGET_TOKENS`, `CHUNK_OVERLAP_TOKENS` tail carried forward, never across a section |
| Describe    | `ingestion/metadata.py`                                   | The flat, versioned chunk metadata schema + heading-path codec                                                        |
| Embed       | `ingestion/embedder.py`                                   | BGE passage/query asymmetry, dimension guard                                                                          |
| Store       | `stores/document_repository.py`                           | Chunks, embeddings, and status in one transaction                                                                     |
| Orchestrate | `ingestion/pipeline.py`                                   | Wires the stages, owns status transitions and failure handling                                                        |

A chunk never crosses a heading boundary, which is what makes the citation
`document → section → page` trustworthy rather than approximate.

### Phase 2 — Retrieval & answering

```
question
   │
   ├─► vector_search   (BGE query embedding → pgvector HNSW, top VECTOR_CANDIDATE_COUNT)
   └─► lexical_search  (Postgres full-text, top LEXICAL_CANDIDATE_COUNT)
                 │
                 ▼
          fusion.py — RRF:  score(d) = Σ  w_s / (k + rank_s(d))
                 │
                 ▼
      hydrate SHORTLIST_CANDIDATE_COUNT from Postgres
                 │
                 ▼
      reranker.py — cross-encoder rescores the shortlist
                 │
                 ▼
      diversity.py — take TOP_K, max MAX_CHUNKS_PER_DOCUMENT per source
                 │
                 ▼
   LangGraph:  retrieve ─┬─(hits)──► generate ──► cite ──► END
                         └─(none)──► fallback ──────────► END
```

RRF is used rather than score normalisation because cosine similarity and the
full-text rank
scores live on incompatible scales; ranks are all they need to have in common.

With `RERANKER_ENABLED`, fusion no longer decides the final order — it only has
to get the right chunks into a shortlist of `SHORTLIST_CANDIDATE_COUNT`, which a
cross-encoder then reorders. The bi-encoder embeds query and passage
separately and never compares them directly; the cross-encoder scores the pair
jointly, which is more accurate at the cost of one forward pass per candidate.
That is why it only ever runs on a shortlist. Measure it before trusting it —
see below.

### Document diversity

Pure relevance ranking answers "which chunks best match this query". For a
comparison — _"how does my resume line up against this job description"_ — that
is the wrong objective. The best six chunks may all come from the longer
document, and the question then becomes structurally unanswerable no matter how
good the ranking is.

`MAX_CHUNKS_PER_DOCUMENT` caps how many of the `TOP_K` slots one document may
occupy (3 of 6 by default), trading a little relevance for the coverage such
questions need. When there are too few distinct documents to fill the window,
displaced chunks are backfilled, so a single-document corpus still gets a full
context block rather than a third of one.

The retrieval benchmark deliberately does **not** apply the cap: its gold set
asks single-section questions, where capping per-document share can only push
the correct chunk out. Measuring a coverage feature against a precision
benchmark would understate it.

The `cite` node validates every `[n]` marker the model emitted against the
context block that was actually sent. Markers pointing at sources that were not
supplied are dropped, so a hallucinated citation cannot reach the UI.

---

## Benchmarking retrieval

`backend/evaluation/` is a standalone harness that measures every retrieval
configuration against a reviewed gold set. It lives outside `app/` because
none of it belongs on the request path.

```bash
# 1. draft questions from your ingested corpus (Groq paraphrases them)
docker compose exec api python -m evaluation generate --email you@example.com

# 2. accept / edit / reject each one — this step is what makes it defensible
docker compose exec -it api python -m evaluation review

# 3. benchmark all four retrieval configurations
docker compose exec api python -m evaluation run --email you@example.com

# 4. benchmark answer quality (RAGAS + citation integrity)
docker compose exec api python -m evaluation generation --email you@example.com
```

Results are written to `/data/evaluation/results/` as JSON and Markdown.

**What is measured**

| Configuration          | What it isolates                        |
| ---------------------- | --------------------------------------- |
| Lexical only           | Postgres full-text baseline             |
| Dense only             | What a typical RAG implementation ships |
| Hybrid RRF             | Value of fusing the two                 |
| Hybrid + cross-encoder | Value of reranking the shortlist        |

Per configuration: Hit@k, MRR, nDCG@k, and p50/p95 latency broken out by stage
(vector, lexical, fusion, hydrate, rerank). Hit rate alone cannot tell rank 1 from
rank 6 — nDCG is what shows whether reranking improved the _ordering_ rather
than just membership. Latency excludes answer generation, which is bounded by
the LLM provider rather than by retrieval.

### Generation quality — two independent views

**RAGAS** scores faithfulness, response relevancy, and context precision with
an LLM judge. The judge is Groq and the embeddings are the same local BGE model
used for retrieval, so evaluation needs no extra API key and no second
embedding space. Adding `reference_answer` to gold questions additionally
enables context recall; without it the harness runs the reference-free subset
rather than silently reporting nothing.

**Citation integrity** is counted, not judged: how many `[n]` markers the model
emitted that pointed outside the supplied context, and therefore how often the
pipeline's guard actually fires. These are exact numbers, and they are the more
defensible of the two.

They are reported side by side on purpose. If the judge calls an answer
faithful while the counter shows the model invented a source number, that
disagreement is the interesting result — and it is the kind of thing a pure
RAGAS score hides.

> RAGAS changes its public API between minor releases. Every import of it is
> confined to `evaluation/ragas_adapter.py`, so an upgrade touches one file.

**Two things the harness does deliberately**

_Reports a confidence interval._ At n=30, a hit rate of 90% carries a 95%
Wilson interval of roughly 74–97%. Quoting the bare number invites a question
you cannot answer; quoting the interval answers it first.

_Refuses to grade its own homework._ Questions generated from a passage tend to
quote it, and a quoted question retrieves its source trivially — every
configuration then scores near 100% and the benchmark measures nothing. The
drafting prompt forbids reusing distinctive wording, and the review step exists
because no prompt makes that guarantee reliable. An unreviewed gold set
measures the generator, not the retriever.

---

## Authentication and data isolation

Sign-in issues a JWT delivered as an **httpOnly, SameSite=Lax cookie**. The
token is never reachable from JavaScript, so an XSS payload cannot exfiltrate a
session. The frontend sends `credentials: 'include'` on every request and never
handles the token itself.

Passwords are bcrypt-hashed at `BCRYPT_ROUNDS` cost. Inputs longer than 72
bytes are rejected rather than silently truncated, which is what bcrypt would
otherwise do. Login answers "Incorrect email or password" for both a missing
account and a wrong password, so the form cannot be used to enumerate accounts.

**Isolation is enforced in four independent places**, so no single mistake
exposes another user's data:

| Layer          | Mechanism                                                                                                                                                                         |
| -------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Vector search  | `WHERE owner_id = ...` is in the same statement as the HNSW scan, with `hnsw.iterative_scan` on, so a filtered query returns the best matches within the filter — not the filtered remains of a global top-N |
| Lexical search | The owner predicate is applied _before_ the `LIMIT`, so a user's results are never another user's leftovers                                                                                                  |
| Postgres reads | Every repository query carries `owner_id` in its `WHERE` clause; ownership is enforced by the query, not by the caller                                                            |
| Hydration      | `get_chunks_by_ids` re-checks ownership even though both searches already filtered, so a future change to either search cannot become a leak                                      |

Another user's document or chat session returns 404, not 403 — existence itself
is not disclosed. Uploads are deduplicated **per owner**, so two users
uploading the same file each get their own document; the file on disk is shared
and only unlinked once no document anywhere references its checksum.

`/api/v1/health` is deliberately public and reports only global counts — it is
the Docker healthcheck probe. Everything else requires a session.

### Abuse limits

`login` is limited per `(client address, email)` — one attacker cannot lock a
victim out by hammering their address, and cannot dodge the limit by rotating
emails. A successful sign-in resets the key, so your own typos never lock you
out. `register` is limited per address, because signup is the cheapest way to
burn disk and embedding CPU.

The client address comes from `X-Forwarded-For`, read from the right by
`TRUSTED_PROXY_HOPS`. **Set this to 0 if you expose the API without a proxy** —
otherwise a caller can prepend their own header and lift their own limit.

Per-account caps (`MAX_DOCUMENTS_PER_USER`, `MAX_STORAGE_BYTES_PER_USER`) are
checked twice: cheaply before the upload is streamed, and again against the
real byte count once it is known. `MAX_UPLOAD_BYTES` only bounds a single file;
without these, one account could fill the volume for everyone.

The limiter is per-process. Behind several API instances the effective limit
multiplies by the instance count — still a bound, but not exact. Moving to
Redis is the upgrade path and the call sites do not change.

### Startup refuses to boot insecurely

`JWT_SECRET_KEY` has **no default in code**. It is a required setting, so a
missing value fails while `Settings` is being constructed — before a single
route is registered. There is no fallback that could be shipped by accident.

`app/startup_checks.py` then rejects a secret shorter than
`JWT_SECRET_MIN_LENGTH` (32), because a short HS256 key can be recovered
offline from one captured token and used to forge a session for any account.
Insecure cookies and a missing Groq key log loud warnings instead of blocking.

Never hard-code a secret in `config.py` — it is committed. Set it in `.env` or
your platform's secret store.

### Where secrets live

| Secret              | Source of truth                         | Committed default                              |
| ------------------- | --------------------------------------- | ---------------------------------------------- |
| `JWT_SECRET_KEY`    | `.env`                                  | **none — required**; import fails without it   |
| `GROQ_API_KEY`      | `.env`                                  | empty; warns at startup                        |
| `POSTGRES_PASSWORD` | `.env`                                  | empty; **compose refuses to start** without it |
| `DATABASE_URL`      | optional override for managed platforms | unset; assembled from `POSTGRES_*`             |

The connection URL is built in `app/db/url.py` with SQLAlchemy's
`URL.create`, which escapes each component. It is never string-formatted, so a
password containing `@`, `:`, `/` or `%` cannot relocate the hostname — the
failure mode that produces a baffling `Name or service not known`. Both the API
and Alembic log the sanitised target (`user@host:port/database`) before
connecting, so a misconfigured URL is visible immediately.

No file in the repository contains a credential that works against anything.
`.env` is gitignored; `.env.example` holds placeholders only. If a real secret
has ever been committed, rotate it — removing it from the working tree does not
remove it from git history.

---

## Layout

```
hybrid-rag/
├─ docker-compose.yml
├─ .env.example
├─ .github/workflows/ci.yml        lint · tests · migrations · image builds
└─ backend/
   ├─ alembic/                     migrations
   ├─ evaluation/                  benchmark harness (not on the request path)
   │  ├─ generate.py · review.py   gold set drafting and human review
   │  ├─ metrics.py                Hit@k · MRR · nDCG · Wilson interval
   │  ├─ citation_metrics.py       exact citation integrity counts
   │  ├─ configurations.py         the four retrieval ablations
   │  ├─ ragas_adapter.py          the only file that imports RAGAS
   │  ├─ answers.py                full-pipeline answer generation
   │  └─ runner.py · generation_runner.py · report.py
   ├─ tests/
   └─ app/
      ├─ config.py                 EVERY tunable constant, declared once
      ├─ errors.py                 domain exceptions → HTTP statuses
      ├─ main.py                   app assembly + lifespan only
      ├─ worker.py                 `python -m app.worker` entry point
      ├─ startup_checks.py         fail-closed config validation
      ├─ db/          session.py · models.py · url.py · pgvector_support.py
      ├─ observability/            context · timing · logging_config
      │                            middleware · db_timing
      ├─ jobs/        queue.py (claim · retry · reap) · worker.py (the loop)
      ├─ security/    password.py (bcrypt) · tokens.py (JWT) · rate_limit.py
      ├─ schemas/     auth · document · chat · ingestion · retrieval · health
      ├─ ingestion/   tokenizer · chunker · metadata · embedder · pipeline
      │  └─ loaders/  base · pdf_loader · markdown_loader · registry
      ├─ stores/      document_repository · chat_repository · user_repository
      ├─ retrieval/   vector_search · lexical_search · fusion · reranker
      │               diversity · hydration · hybrid_retriever
      ├─ generation/  prompt · llm · citations
      ├─ graph/       state · nodes · pipeline
      └─ api/         deps.py + routes/{auth,documents,chat,health}.py
└─ frontend/
   └─ src/
      ├─ config.js                 every frontend constant
      ├─ styles.css                dark base · per-document hues
      ├─ api/client.js             the only module that calls fetch
      ├─ lib/documentColor.js      stable hue per document id
      ├─ hooks/       useAuth · useChat · useDocuments
      └─ components/  LoginPage · Workspace · SessionSidebar · ChatWindow
                      MessageBubble · CitationList · Composer · DocumentPanel
```

`App.jsx` only decides _which_ of `LoginPage` or `Workspace` to render.
`Workspace` is where `useChat` and `useDocuments` live, so those hooks never
fire a request while signed out. It is keyed on the user id, which discards
every cached document and conversation when the account changes.

**One responsibility per file.** The chunker does not embed. The embedder does
not store. The retriever does not score — `lexical_search` and `vector_search`
score, `fusion` merges, `hybrid_retriever` only coordinates. `pipeline.py`
files contain wiring and error handling, never algorithms.

**No magic numbers.** `backend/app/config.py` and `frontend/src/config.js` are
the only files containing literals that a reader might want to change.

---

## Running it

```bash
cp .env.example .env
# put a real GROQ_API_KEY in .env  (https://console.groq.com/keys)
# and a real JWT_SECRET_KEY:
#   python -c "import secrets; print(secrets.token_urlsafe(48))"

docker compose up --build
```

Open the UI and register — the first screen is sign-in / create-account.

> **Upgrading from an older version.** Two migrations are destructive and say so
> in their own docstrings:
>
> - `0002` deletes documents and chats created before accounts existed, since
>   those rows cannot be attributed to an owner.
> - `0003` moves vectors out of ChromaDB into Postgres. Chroma's vectors cannot
>   be migrated by SQL, so every chunk is deleted and every document is queued
>   for re-ingestion from the original file, which is still on disk. No upload,
>   account, or chat history is lost; every document is re-embedded, costing
>   about what the original upload did. Afterwards `/data/chroma` is dead weight
>   and can be deleted by hand — `0003` deliberately leaves it, because a
>   migration should not destroy the only copy of data it cannot restore.

Before exposing this beyond localhost, set `AUTH_COOKIE_SECURE=true` (requires
HTTPS) and a generated `JWT_SECRET_KEY`.

- UI — http://localhost:5173
- API docs — http://localhost:8000/docs
- Health — http://localhost:8000/api/v1/health

The UI calls the API at the **relative** path `/api/v1`; nginx proxies it to
the `api` service. Same origin means no CORS preflight and a first-party
session cookie — `http://127.0.0.1:5173` and `http://localhost:5173` both work,
which they would not with a cross-origin API URL. `vite.config.js` mirrors the
same proxy so `npm run dev` behaves identically.

Migrations run automatically on API start (`entrypoint.sh`). The first ingest
downloads the embedding model (~130 MB) into the `rag-data` volume, so the very
first upload is slower than subsequent ones.

### Local development

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
export POSTGRES_PASSWORD=...          # same value as in .env
export JWT_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
export AUTH_COOKIE_SECURE=false   # required over plain http://localhost
alembic upgrade head
uvicorn app.main:app --reload
```

```bash
cd frontend
npm install
npm run dev
```

### Checks

```bash
cd backend
pip install -r requirements-dev.txt

pytest          # 104 unit tests, no network and no database required
ruff check .
ruff format --check .
```

Unit tests are deliberately offline: the chunker tests inject a word-counting
`TokenCounter`, so packing behaviour is asserted without downloading a
tokenizer.

Two suites need a real database, because what they test only exists in
Postgres — an index filter applied before the limit, a generated column, a
partial unique index, `SKIP LOCKED`. They **skip themselves** when
`TEST_DATABASE_URL` is unset so `pytest` still works with nothing running:

```bash
docker run --rm -d -p 5433:5432 \
  -e POSTGRES_USER=rag -e POSTGRES_PASSWORD=rag -e POSTGRES_DB=rag_test \
  --name rag-test-db pgvector/pgvector:pg16

TEST_DATABASE_URL=postgresql+psycopg://rag:rag@localhost:5433/rag_test pytest
```

CI (`.github/workflows/ci.yml`) runs lint, both test suites against a real
pgvector service, `alembic upgrade head` from an empty database plus a
downgrade/upgrade round trip, a schema assertion that the HNSW and GIN indexes
actually exist, and both Docker builds. It also fails if the integration tests
report as skipped — otherwise a broken database service would show up as a
green build with the most important tests quietly not running.

---

## The ingestion queue

Ingestion runs in a separate process (`docker compose` service `worker`,
or `python -m app.worker`). The queue is a Postgres table, claimed with
`SELECT ... FOR UPDATE SKIP LOCKED`.

Why a table and not Redis or a broker: the jobs are about rows in this
database, and a broker is a second system that can disagree with it — a job
that says "ready" for a document that was deleted, or a document stuck in
`processing` with nothing queued. At ingestion's timescale (minutes of CPU per
document) the queue is never the bottleneck, so the throughput a broker would
buy has nothing to spend itself on.

Three mechanisms stop a crash from stranding a document:

| Mechanism | Covers |
| --- | --- |
| The claim is a transaction | A worker killed between claiming and finishing never committed, so the row is untouched |
| Heartbeats + reaper | A worker killed *after* committing its claim. The reaper requeues jobs whose heartbeat went stale |
| Bounded attempts | A document that fails every time ends as `dead` with its error recorded, rather than cycling forever |

Failures are classified. `PermanentIngestionError` — an empty PDF, a missing
file, a deleted document — goes straight to `dead`, because retrying cannot
change the answer and burning three attempts only delays telling the user.
Everything else retries with exponential backoff.

Scale it with `docker compose up -d --scale worker=3`. That is safe by
construction: `SKIP LOCKED` gives each worker a different job, and no worker
holds an index the others cannot see.

```bash
# What the queue is doing right now
curl -s localhost:8000/api/v1/health | python -m json.tool
```

---

## Observability

Every request gets an id — taken from `X-Request-ID` if a proxy sent a clean
one, otherwise generated — echoed back in the response header and attached to
every log record the request produces, including the ingestion job it queues.
The user id joins it the moment authentication resolves.

Logs are JSON by default (`LOG_RENDERER=console` for a terminal). Each request
ends in one record carrying a per-stage latency breakdown:

```json
{
  "timestamp": "2026-08-31T09:12:44.108+00:00",
  "level": "INFO",
  "logger": "app.request",
  "message": "POST /api/v1/chat/sessions/.../query -> 200 in 2793 ms",
  "request_id": "9f2c40b71ae83d15",
  "user_id": "8c1d...",
  "duration_ms": 2793.4,
  "stages": {
    "database": 31.2,
    "embed_query": 18.7,
    "vector_search": 79.5,
    "lexical_search": 41.3,
    "fusion": 0.4,
    "hydrate": 12.8,
    "rerank": 118.6,
    "llm": 2489.1
  }
}
```

Set `LOG_TIMING_BREAKDOWN=true` to also print it as a readable block:

```
Request: 9f2c40b71ae83d15
  Database        31 ms
  Embed query     19 ms
  Vector search   80 ms
  Lexical search  41 ms
  Fusion           0 ms
  Hydrate         13 ms
  Reranking      119 ms
  LLM           2489 ms
  Total         2793 ms
  Unattributed     1 ms
```

Database time is measured by hooking SQLAlchemy's cursor events, so it counts
what actually executed rather than what the code looks like it does — an N+1
pattern shows up here as a large `database` total that reading the source
would not have revealed. `Unattributed` is deliberately shown rather than
hidden: a large gap means time is going somewhere nothing is measuring, which
is itself the finding.

Requests slower than `SLOW_REQUEST_MS` log at `WARNING`, so a latency
regression surfaces without reading every line.

---

## Streaming

`POST /chat/sessions/{id}/query/stream` returns Server-Sent Events:

| Event | When | Payload |
| --- | --- | --- |
| `meta` | once, after retrieval | request id, `grounded`, and the sources retrieved |
| `token` | many | one content delta |
| `done` | once | persisted message id, **validated** citations, stage timings |
| `error` | instead of `done` | a message safe to show the user |

Citation validation is not incremental, and that shapes the protocol. A marker
is only trustworthy once the full text exists — `[1` is not yet `[12]` — so
tokens stream immediately for latency and the validated citation list arrives
at the end. Until `done` lands the UI renders the text plainly; resolving
markers mid-stream would flash every one of them from broken to valid as the
answer completed.

The assistant message is persisted only after a complete answer. A stream cut
off halfway leaves no message, so a reload shows the question unanswered
rather than a truncated reply presented as final.

`/query` (non-streaming) still exists and is what the benchmark harness uses.

---

## Known limitations at scale

This runs correctly as deployed and is honest about where it would stop.

**No caching layer.** Rate limiting is per-process (`security/rate_limit.py`),
so with N API replicas a caller gets N times the configured allowance. The
limits are conservative enough that this is an abuse-resistance weakness, not
a correctness one. Redis and a shared counter is the fix.

**Polling, not push.** Workers poll for jobs every `JOB_POLL_INTERVAL_SECONDS`
rather than using `LISTEN`/`NOTIFY`. That is a couple of seconds of latency on
work that takes minutes, in exchange for not maintaining a persistent
connection and its reconnect path. Worth revisiting only if jobs get small and
frequent.

**HNSW recall is a setting, not a guarantee.** `HNSW_EF_SEARCH` bounds how
hard the index looks. Filtered search relies on `hnsw.iterative_scan`, which
needs pgvector ≥ 0.8; on an older server the API logs a warning at first query
and filtered searches may quietly return fewer candidates than requested.

**The lexical scorer is not BM25.** `ts_rank_cd` has no term-frequency
saturation and a coarser length normalisation than BM25's `b`. Fusion consumes
ranks rather than scores, so this matters less than it sounds — but *how much*
less is an empirical question, and `backend/evaluation` is the tool for
answering it rather than assuming.

**One embedding model, no versioning.** Changing `EMBEDDING_MODEL_NAME`
invalidates every stored vector. There is a dimension guard that fails loudly
on a mismatch, but no online re-embedding path: the migration is to re-ingest.

**No autoscaling signal.** `/health` reports queue depth by status, which is
the number you would scale workers on, but nothing consumes it. There is no
metrics endpoint and no tracing — the structured logs carry the same stage
timings, so a collector can derive them, but Prometheus and OpenTelemetry are
not wired up.

**Files are local.** Uploads live on a shared volume, so the API and workers
must sit on the same host or share network storage. S3 would remove that
constraint.

---

## Tuning notes

| Setting                                           | Effect                                                                                                      |
| ------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| `CHUNK_TARGET_TOKENS`                             | Larger → more context per hit, fuzzier citations. 512 matches the BGE input window.                         |
| `CHUNK_OVERLAP_TOKENS`                            | Guards against answers split across a chunk boundary.                                                       |
| `RRF_K`                                           | Higher flattens the contribution of top ranks; 60 is the value from the original RRF paper.                 |
| `RRF_LEXICAL_WEIGHT`                              | Below 1.0 favours semantic matching. Raise it for corpora full of exact identifiers, part numbers, or code. |
| `VECTOR_CANDIDATE_COUNT` / `LEXICAL_CANDIDATE_COUNT` | Fusion can only rerank what it is given — widen these before widening `TOP_K`.                              |
| `GROQ_TEMPERATURE`                                | Kept at 0.1: grounded answering wants determinism, not variety.                                             |

Changing `EMBEDDING_MODEL_NAME` invalidates the existing index. `Embedder`
refuses to start if the model's dimension disagrees with `EMBEDDING_DIMENSION`,
which turns a silent retrieval-quality collapse into a startup error.
