# Folder structure

**47** backend modules · **15** evaluation modules · **14** test files ·
**19** frontend source files · **2** migrations

Two rules hold everywhere: one responsibility per file, and every tunable
number declared once in a config module and imported. `app/` contains only
request-path code; `evaluation/` never runs in production.

```
rag-chatbot/
├── docker-compose.yml            postgres · api · frontend
├── .env.example                  every secret and tunable, with placeholders
├── .gitignore
├── README.md                     architecture, benchmarks, deployment
├── FOLDER_STRUCTURE.md           this file
├── resume-content.md
│
├── backend/
│   ├── Dockerfile                CPU-only torch, optional eval extras
│   ├── entrypoint.sh             migrate, then serve
│   ├── alembic.ini
│   ├── pytest.ini
│   ├── ruff.toml
│   ├── requirements.txt          runtime
│   ├── requirements-dev.txt      pytest, ruff, vulture
│   ├── requirements-eval.txt     RAGAS + LangChain (optional)
│   │
│   ├── alembic/
│   │   ├── env.py                builds the URL in code, not via configparser
│   │   ├── script.py.mako
│   │   └── versions/
│   │       ├── 0001_initial_schema.py
│   │       └── 0002_user_accounts.py
│   │
│   ├── app/                                    ← request path only
│   │   ├── config.py             EVERY tunable constant, declared once
│   │   ├── errors.py             domain exceptions → HTTP status codes
│   │   ├── logging_config.py
│   │   ├── startup_checks.py     fail-closed validation; refuses weak secrets
│   │   ├── main.py               app assembly + lifespan, nothing else
│   │   │
│   │   ├── api/
│   │   │   ├── deps.py           get_db · get_current_user
│   │   │   └── routes/
│   │   │       ├── auth.py       register · login · logout · me
│   │   │       ├── documents.py  upload · list · delete
│   │   │       ├── chat.py       sessions · history · query
│   │   │       └── health.py     public readiness probe
│   │   │
│   │   ├── db/
│   │   │   ├── models.py         users · documents · chunks · sessions · messages
│   │   │   ├── session.py        engine + session factory
│   │   │   └── url.py            URL.create assembly; escapes any password
│   │   │
│   │   ├── schemas/              auth · document · chat · ingestion
│   │   │                         retrieval · health
│   │   │
│   │   ├── security/
│   │   │   ├── password.py       bcrypt, cost 12
│   │   │   ├── tokens.py         JWT encode/decode
│   │   │   └── rate_limit.py     sliding window + proxy-aware client identity
│   │   │
│   │   ├── ingestion/                          ← PHASE 1
│   │   │   ├── loaders/
│   │   │   │   ├── base.py               loader contract
│   │   │   │   ├── pdf_loader.py         heading recovery: font size + TOC
│   │   │   │   ├── markdown_loader.py    ATX heading hierarchy
│   │   │   │   └── registry.py           extension → loader; the only format list
│   │   │   ├── tokenizer.py      counts with the embedding model's own tokenizer
│   │   │   ├── chunker.py        512/64 packing, never crosses a section
│   │   │   ├── metadata.py       flat versioned Chroma schema + heading codec
│   │   │   ├── embedder.py       BGE passage/query asymmetry, dimension guard
│   │   │   └── pipeline.py       wiring and failure handling; no algorithms
│   │   │
│   │   ├── stores/
│   │   │   ├── vector_store.py           ChromaDB
│   │   │   ├── document_repository.py    owner-scoped; quotas
│   │   │   ├── chat_repository.py        owner-scoped history
│   │   │   └── user_repository.py
│   │   │
│   │   ├── retrieval/                          ← PHASE 2
│   │   │   ├── vector_search.py    dense, filtered pre-ANN-cut
│   │   │   ├── bm25_search.py      lexical, filtered pre-truncation
│   │   │   ├── fusion.py           Reciprocal Rank Fusion
│   │   │   ├── reranker.py         cross-encoder over the shortlist
│   │   │   ├── diversity.py        caps one document's share of top-k
│   │   │   ├── hydration.py        chunk row → DTO, in one place
│   │   │   ├── hybrid_retriever.py coordination only
│   │   │   └── index_builder.py    keeps BM25 in sync with Postgres
│   │   │
│   │   ├── generation/
│   │   │   ├── prompt.py         numbered context block + system prompt
│   │   │   ├── llm.py            the only module that calls Groq
│   │   │   └── citations.py      validates [n] markers, drops invented ones
│   │   │
│   │   └── graph/
│   │       ├── state.py          LangGraph state
│   │       ├── nodes.py          retrieve · generate · cite · fallback
│   │       └── pipeline.py       graph assembly with conditional branch
│   │
│   ├── evaluation/                             ← NOT on the request path
│   │   ├── config.py             harness constants, separate from app config
│   │   ├── schema.py             gold set + report shapes
│   │   ├── corpus.py             reads the benchmark needs, the API doesn't
│   │   ├── generate.py           Groq drafts paraphrased questions
│   │   ├── review.py             human accept/edit/reject — the honesty step
│   │   ├── goldset.py            load/save gold set and candidates
│   │   ├── metrics.py            Hit@k · MRR · nDCG · Wilson interval
│   │   ├── configurations.py     the four retrieval ablations
│   │   ├── runner.py             executes them with per-stage timing
│   │   ├── answers.py            full-pipeline answer generation
│   │   ├── citation_metrics.py   exact citation integrity counts
│   │   ├── ragas_adapter.py      the ONLY file that imports RAGAS
│   │   ├── generation_runner.py  orchestrates the generation benchmark
│   │   ├── report.py             JSON + Markdown output
│   │   └── __main__.py           generate · review · run · generation
│   │
│   └── tests/
│       ├── conftest.py                   offline tokenizer fake, test secret
│       ├── test_chunker.py               packing, overlap, section boundaries
│       ├── test_markdown_loader.py       heading hierarchy, fenced code
│       ├── test_metadata.py              flat schema, owner key, round-trip
│       ├── test_fusion.py                RRF formula, weights, determinism
│       ├── test_bm25_owner_scope.py      cross-tenant isolation
│       ├── test_diversity.py             per-document cap, backfill, order
│       ├── test_citations.py             marker extraction, hallucination drop
│       ├── test_prompt.py                numbering, context block, history
│       ├── test_password.py              bcrypt, salts, length bounds
│       ├── test_tokens.py                signing, tampering, expiry
│       ├── test_rate_limit.py            window slide, eviction, reset
│       ├── test_startup_checks.py        fail-closed guards
│       ├── test_evaluation_metrics.py    nDCG, Wilson, percentiles
│       └── test_citation_metrics.py      hallucination rate, coverage
│
└── frontend/
    ├── Dockerfile                build → nginx
    ├── nginx.conf                /api proxy · 50m bodies · 180s timeout
    ├── vite.config.js            dev proxy mirroring nginx
    ├── index.html
    ├── package.json
    └── src/
        ├── config.js             every frontend constant
        ├── styles.css
        ├── main.jsx
        ├── App.jsx               chooses LoginPage or Workspace, nothing more
        ├── api/client.js         the only module that calls fetch
        ├── hooks/
        │   ├── useAuth.js        session restore, sign in/up/out
        │   ├── useChat.js        sessions, transcript, ask
        │   └── useDocuments.js   upload, poll while ingesting, delete
        └── components/
            ├── LoginPage.jsx     sign in / register toggle
            ├── Workspace.jsx     mounted only when authenticated
            ├── SessionSidebar.jsx
            ├── ChatWindow.jsx
            ├── MessageBubble.jsx inline citation markers
            ├── CitationList.jsx  document → section → page
            ├── Composer.jsx
            └── DocumentPanel.jsx upload + ingestion status
```

## Where the boundaries are

**`app/` vs `evaluation/`** — nothing in `evaluation/` is imported by the
request path. It reads the same database and calls the same primitives, but the
service never loads it. This is why the four ablations can exist: there is no
"BM25 only" mode of the running system.

**`ragas_adapter.py`** is the only file that imports RAGAS. Its API moves
between minor releases, so an upgrade touches one file rather than the harness.

**`config.py` × 3** — `app/config.py` (runtime), `evaluation/config.py`
(harness), `frontend/src/config.js` (client). No tunable literal lives anywhere
else in the codebase.

---

## Packaging it as a zip

I can't produce the archive from here — the Linux sandbox this session uses
won't start (disk space), so there's no way for me to write a binary file.
Run this in PowerShell instead:

```powershell
$src   = 'D:\rag-chatbot'
$stage = 'D:\rag-chatbot-package'

Remove-Item $stage -Recurse -Force -ErrorAction SilentlyContinue
robocopy $src $stage /E /XD node_modules dist __pycache__ .pytest_cache `
    .ruff_cache .venv .git data /XF .env *.pyc | Out-Null
Compress-Archive -Path "$stage\*" -DestinationPath 'D:\rag-chatbot.zip' -Force
Remove-Item $stage -Recurse -Force

Write-Host "Wrote D:\rag-chatbot.zip"
```

`robocopy` rather than piping file objects into `Compress-Archive`, because
that flattens the directory tree. The excludes matter: `node_modules` is
hundreds of megabytes of reinstallable dependencies, and **`.env` holds your
Groq key, JWT secret, and database password** — it must not go into an archive
you send to anyone.

Verify before sharing:

```powershell
Add-Type -A System.IO.Compression.FileSystem
[IO.Compression.ZipFile]::OpenRead('D:\rag-chatbot.zip').Entries |
    Where-Object { $_.Name -like '*.env*' }
```

That should print nothing.
