# Hybrid RAG

Structure-aware ingestion + hybrid retrieval (BM25 × dense, fused with Reciprocal
Rank Fusion) behind a LangGraph pipeline that returns answers with verifiable
citations down to the document section and page.

Multi-user: each account has its own private knowledge base and its own chat
history. Documents, chunks, vectors, and conversations are all owner-scoped.

- **Backend** — FastAPI, SQLAlchemy 2, Alembic
- **Auth** — bcrypt + JWT in an httpOnly cookie
- **Vectors** — ChromaDB (persistent, cosine)
- **Lexical** — rank_bm25, rebuilt from Postgres on every corpus mutation
- **Embeddings** — `BAAI/bge-small-en-v1.5`, local, CPU, 384-dim
- **Generation** — Groq (`llama-3.3-70b-versatile`)
- **System of record** — Postgres: documents, chunks, chat sessions, message history
- **Frontend** — React 18 + Vite

---

## Architecture

### Phase 1 — Ingestion

```
upload ──► loader ──► chunker ──► metadata ──► embedder ──► Chroma
             │           │           │                        │
        (heading      (token-      (flat,                 Postgres
         hierarchy)    bounded,     versioned              chunks +
                       overlapped)  schema)                 status
```

| Stage       | File                                                      | Responsibility                                                                                                        |
| ----------- | --------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| Load        | `ingestion/loaders/pdf_loader.py`, `markdown_loader.py`   | Raw file → ordered `Section`s carrying a heading path                                                                 |
| Route       | `ingestion/loaders/registry.py`                           | Extension → loader; the only place formats are declared                                                               |
| Count       | `ingestion/tokenizer.py`                                  | Token counts from the _embedding model's own_ tokenizer                                                               |
| Chunk       | `ingestion/chunker.py`                                    | Greedy sentence packing to `CHUNK_TARGET_TOKENS`, `CHUNK_OVERLAP_TOKENS` tail carried forward, never across a section |
| Describe    | `ingestion/metadata.py`                                   | The flat, versioned Chroma metadata schema + heading-path codec                                                       |
| Embed       | `ingestion/embedder.py`                                   | BGE passage/query asymmetry, dimension guard                                                                          |
| Store       | `stores/vector_store.py`, `stores/document_repository.py` | Chroma writes; Postgres writes                                                                                        |
| Orchestrate | `ingestion/pipeline.py`                                   | Wires the stages, owns status transitions and failure handling                                                        |

A chunk never crosses a heading boundary, which is what makes the citation
`document → section → page` trustworthy rather than approximate.

### Phase 2 — Retrieval & answering

```
question
   │
   ├─► vector_search  (BGE query embedding → Chroma, top VECTOR_CANDIDATE_COUNT)
   └─► bm25_search    (in-memory BM25Okapi, top BM25_CANDIDATE_COUNT)
                 │
                 ▼
          fusion.py — RRF:  score(d) = Σ  w_s / (k + rank_s(d))
                 │
                 ▼
      hybrid_retriever — take TOP_K, hydrate from Postgres
                 │
                 ▼
   LangGraph:  retrieve ─┬─(hits)──► generate ──► cite ──► END
                         └─(none)──► fallback ──────────► END
```

RRF is used rather than score normalisation because cosine similarity and BM25
scores live on incompatible scales; ranks are all they need to have in common.

The `cite` node validates every `[n]` marker the model emitted against the
context block that was actually sent. Markers pointing at sources that were not
supplied are dropped, so a hallucinated citation cannot reach the UI.

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
| Chroma         | `where={"owner_id": ...}` applied _before_ the nearest-neighbour cut, so a filtered query returns the best matches within the filter — not the filtered remains of a global top-N |
| BM25           | One shared index (stable IDF) filtered by owner _before_ truncation to `BM25_CANDIDATE_COUNT`                                                                                     |
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

| Secret | Source of truth | Committed default |
|---|---|---|
| `JWT_SECRET_KEY` | `.env` | **none — required**; import fails without it |
| `GROQ_API_KEY` | `.env` | empty; warns at startup |
| `POSTGRES_PASSWORD` | `.env` | empty; **compose refuses to start** without it |
| `DATABASE_URL` | optional override for managed platforms | unset; assembled from `POSTGRES_*` |

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
└─ backend/
   ├─ alembic/                     migrations
   ├─ tests/
   └─ app/
      ├─ config.py                 EVERY tunable constant, declared once
      ├─ errors.py                 domain exceptions → HTTP statuses
      ├─ logging_config.py
      ├─ main.py                   app assembly + lifespan only
      ├─ db/          session.py · models.py
      ├─ startup_checks.py         fail-closed config validation
      ├─ security/    password.py (bcrypt) · tokens.py (JWT) · rate_limit.py
      ├─ schemas/     auth · document · chat · ingestion · retrieval · health
      ├─ ingestion/   tokenizer · chunker · metadata · embedder · pipeline
      │  └─ loaders/  base · pdf_loader · markdown_loader · registry
      ├─ stores/      vector_store · document_repository · chat_repository · user_repository
      ├─ retrieval/   vector_search · bm25_search · fusion · hybrid_retriever · index_builder
      ├─ generation/  prompt · llm · citations
      ├─ graph/       state · nodes · pipeline
      └─ api/         deps.py + routes/{auth,documents,chat,health}.py
└─ frontend/
   └─ src/
      ├─ config.js                 every frontend constant
      ├─ api/client.js             the only module that calls fetch
      ├─ hooks/       useAuth · useChat · useDocuments
      └─ components/  LoginPage · Workspace · SessionSidebar · ChatWindow
                      MessageBubble · CitationList · Composer · DocumentPanel
```

`App.jsx` only decides _which_ of `LoginPage` or `Workspace` to render.
`Workspace` is where `useChat` and `useDocuments` live, so those hooks never
fire a request while signed out. It is keyed on the user id, which discards
every cached document and conversation when the account changes.

**One responsibility per file.** The chunker does not embed. The embedder does
not store. The retriever does not score — `bm25_search` and `vector_search`
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

> **Upgrading from the pre-auth version:** migration `0002` deletes existing
> documents and chats, because rows created before accounts existed cannot be
> attributed to an owner. Chroma is a separate store that migrations do not
> touch, so clear it too: `docker compose down -v`.

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
pytest    # chunking, fusion, citations, metadata, loader, prompt, JWT
          # signing/expiry, bcrypt, BM25 owner isolation, rate limiting,
          # startup guards
ruff check .
vulture app --min-confidence 80    # dead-code sweep
```

The test suite is deliberately offline: the chunker tests inject a
word-counting `TokenCounter` so packing behaviour is asserted without
downloading a tokenizer.

---

## API

---

## Tuning notes

| Setting                                           | Effect                                                                                                      |
| ------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| `CHUNK_TARGET_TOKENS`                             | Larger → more context per hit, fuzzier citations. 512 matches the BGE input window.                         |
| `CHUNK_OVERLAP_TOKENS`                            | Guards against answers split across a chunk boundary.                                                       |
| `RRF_K`                                           | Higher flattens the contribution of top ranks; 60 is the value from the original RRF paper.                 |
| `RRF_BM25_WEIGHT`                                 | Below 1.0 favours semantic matching. Raise it for corpora full of exact identifiers, part numbers, or code. |
| `VECTOR_CANDIDATE_COUNT` / `BM25_CANDIDATE_COUNT` | Fusion can only rerank what it is given — widen these before widening `TOP_K`.                              |
| `GROQ_TEMPERATURE`                                | Kept at 0.1: grounded answering wants determinism, not variety.                                             |

Changing `EMBEDDING_MODEL_NAME` invalidates the existing index. `Embedder`
refuses to start if the model's dimension disagrees with `EMBEDDING_DIMENSION`,
which turns a silent retrieval-quality collapse into a startup error.
