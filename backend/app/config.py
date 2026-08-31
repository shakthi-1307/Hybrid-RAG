"""Single source of truth for every tunable constant in the application.

Rule: no module may hard-code a threshold, size, model name, or limit.
Everything is declared here once and imported as ``settings.<NAME>``.
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file="../.env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    # ------------------------------------------------------------------ app
    APP_NAME: str = "Hybrid RAG"
    APP_VERSION: str = "1.0.0"
    API_PREFIX: str = "/api/v1"
    # The UI is served same-origin behind the nginx /api proxy, so it needs no
    # CORS grant. This list only covers tools hitting the API port directly.
    # localhost and 127.0.0.1 are distinct origins to a browser — list both.
    CORS_ORIGINS: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    LOG_LEVEL: str = "INFO"
    # "json" for anything that ships logs somewhere (one object per line, with
    # request_id and user_id on every record). "console" for a human reading a
    # terminal. The two carry identical fields; only the rendering differs.
    LOG_RENDERER: str = "json"
    LOG_CONSOLE_FORMAT: str = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"
    # Header a proxy may use to pass a request id inward. Absent or malformed,
    # the middleware mints one. Echoed back on every response so a user can
    # quote it in a bug report and land on the exact request.
    REQUEST_ID_HEADER: str = "X-Request-ID"
    REQUEST_ID_MAX_LENGTH: int = 64
    # Emit the per-stage latency breakdown as an indented block after the
    # request line. Readable during development, noise in aggregation — the
    # same numbers are always on the structured record as "stages".
    LOG_TIMING_BREAKDOWN: bool = False
    # Requests slower than this are logged at WARNING instead of INFO, so a
    # latency regression surfaces without reading every line.
    SLOW_REQUEST_MS: float = 5_000.0

    # -------------------------------------------------------------- storage
    UPLOAD_DIR: Path = Path("/data/uploads")
    # Two ways in, checked in this order by app.db.url:
    #   1. DATABASE_URL — a complete URL, which is what managed platforms hand
    #      you. Used verbatim.
    #   2. POSTGRES_* parts — assembled with SQLAlchemy's URL.create, which
    #      escapes the password properly. Never format a password into a URL by
    #      hand: @ : / and % all carry meaning in the authority section, and a
    #      stray one silently relocates the hostname.
    DATABASE_DRIVER: str = "postgresql+psycopg"
    DATABASE_URL: str | None = None
    POSTGRES_USER: str = "rag"
    POSTGRES_PASSWORD: str = ""
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "rag"
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_RECYCLE_SECONDS: int = 1800

    # ------------------------------------------------------------------ auth
    # Required, with no default: read from .env (or the platform's secret
    # store) or the process refuses to construct its settings at all. There is
    # deliberately no fallback value that could be shipped by accident.
    JWT_SECRET_KEY: str
    JWT_SECRET_MIN_LENGTH: int = 32
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRY_MINUTES: int = 60 * 24 * 7
    AUTH_COOKIE_NAME: str = "rag_session"
    # Set false for plain-HTTP local development: browsers silently discard a
    # Secure cookie sent over http://, which looks like login failing at random.
    AUTH_COOKIE_SECURE: bool = True
    AUTH_COOKIE_SAMESITE: str = "lax"
    BCRYPT_ROUNDS: int = 12
    PASSWORD_MIN_LENGTH: int = 10
    # bcrypt silently ignores input past 72 bytes, so reject it instead.
    PASSWORD_MAX_BYTES: int = 72

    # ---------------------------------------------------------- rate limiting
    # How many proxies sit in front of the API. The client IP is taken that
    # many entries from the right of X-Forwarded-For, so a caller cannot spoof
    # their identity by sending their own header. Set to 0 if the API is
    # exposed directly with no proxy.
    TRUSTED_PROXY_HOPS: int = 1
    LOGIN_RATE_LIMIT_ATTEMPTS: int = 8
    LOGIN_RATE_LIMIT_WINDOW_SECONDS: int = 300
    REGISTER_RATE_LIMIT_ATTEMPTS: int = 5
    REGISTER_RATE_LIMIT_WINDOW_SECONDS: int = 3600
    # Bounds the limiter's memory; stale keys are evicted past this many.
    RATE_LIMIT_MAX_TRACKED_KEYS: int = 10_000

    # ---------------------------------------------------------- per-user caps
    MAX_DOCUMENTS_PER_USER: int = 100
    MAX_STORAGE_BYTES_PER_USER: int = 500 * 1024 * 1024

    # ------------------------------------------------------------- ingestion
    MAX_UPLOAD_BYTES: int = 50 * 1024 * 1024
    UPLOAD_STREAM_CHUNK_BYTES: int = 1024 * 1024
    METADATA_SCHEMA_VERSION: int = 1
    HEADING_PATH_SEPARATOR: str = " > "

    # PDF structure detection
    PDF_HEADING_SIZE_RATIO: float = 1.12
    PDF_HEADING_MAX_WORDS: int = 18
    MAX_HEADING_DEPTH: int = 4

    # Structural chunking
    CHUNK_TARGET_TOKENS: int = 512
    CHUNK_OVERLAP_TOKENS: int = 64
    CHUNK_MIN_TOKENS: int = 32

    # ------------------------------------------------------------- embedding
    EMBEDDING_MODEL_NAME: str = "BAAI/bge-small-en-v1.5"
    EMBEDDING_DIMENSION: int = 384
    EMBEDDING_BATCH_SIZE: int = 32
    EMBEDDING_DEVICE: str = "cpu"
    EMBEDDING_NORMALIZE: bool = True
    EMBEDDING_QUERY_PREFIX: str = (
        "Represent this sentence for searching relevant passages: "
    )

    # ---------------------------------------------------------- vector index
    # HNSW build parameters. Higher values build a slower, more accurate graph.
    # Changing either requires rebuilding the index (see alembic 0003).
    HNSW_M: int = 16
    HNSW_EF_CONSTRUCTION: int = 64
    # Search-time candidate list. Must exceed VECTOR_CANDIDATE_COUNT or the
    # index cannot return that many neighbours at all.
    HNSW_EF_SEARCH: int = 100
    # pgvector applies the WHERE clause *after* walking the graph, so a
    # single-user query over a many-user corpus can come back short — the same
    # "filtered remains of a global top-N" failure the design exists to avoid.
    # Iterative scan makes the index keep walking until it has enough rows that
    # survive the filter. "relaxed_order" allows slight reordering within the
    # candidate set in exchange for far fewer wasted scans; RRF consumes ranks
    # from this list and re-sorts anyway. Requires pgvector >= 0.8.
    HNSW_ITERATIVE_SCAN: str = "relaxed_order"
    HNSW_MAX_SCAN_TUPLES: int = 20_000

    # ------------------------------------------------------------- retrieval
    VECTOR_CANDIDATE_COUNT: int = 40
    LEXICAL_CANDIDATE_COUNT: int = 40
    # Postgres full-text config used for both indexing and querying. The two
    # must match: a tsvector built with 'english' will not match a tsquery
    # parsed with 'simple'.
    TEXT_SEARCH_CONFIG: str = "english"
    # ts_rank_cd normalisation flags, OR-ed together. 1 divides the rank by
    # 1 + log(document length), which is the closest analogue Postgres offers
    # to BM25's length normalisation (the 'b' parameter). Without it, long
    # chunks win on raw term frequency alone.
    TEXT_RANK_NORMALIZATION: int = 1
    # Guards against a pathological query expanding into a huge tsquery.
    MAX_QUERY_TERMS: int = 40
    RRF_K: int = 60
    RRF_VECTOR_WEIGHT: float = 1.0
    RRF_LEXICAL_WEIGHT: float = 0.8
    TOP_K: int = 6

    # ------------------------------------------------------------- reranking
    # A bi-encoder embeds query and passage separately and never sees the pair;
    # a cross-encoder scores them jointly, which orders the shortlist far more
    # accurately at the cost of one forward pass per candidate. Run the
    # benchmark (see backend/evaluation) before trusting the default.
    RERANKER_ENABLED: bool = True
    RERANKER_MODEL_NAME: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    RERANKER_BATCH_SIZE: int = 32
    # The shortlist fusion hands downstream. It feeds both the cross-encoder
    # and diversity selection, so it stays wide even with reranking off —
    # neither can promote a chunk that was never shortlisted.
    SHORTLIST_CANDIDATE_COUNT: int = 40

    # ------------------------------------------------------------- diversity
    # Ceiling on how many of the TOP_K chunks any single document may occupy.
    # At 3 of 6, a long document cannot crowd every other source out of the
    # context window — which is what makes "compare A against B" answerable.
    # Raise it toward TOP_K to favour pure relevance over coverage.
    MAX_CHUNKS_PER_DOCUMENT: int = 3

    # ------------------------------------------------------------ job queue
    # Ingestion runs in a separate worker process, so a crash mid-document
    # cannot take the API down and a restart does not strand the document.
    # The queue is a Postgres table claimed with SELECT ... FOR UPDATE SKIP
    # LOCKED: no extra infrastructure, and the claim is transactional, so a
    # worker that dies holding a job releases it rather than losing it.
    JOB_POLL_INTERVAL_SECONDS: float = 2.0
    JOB_MAX_ATTEMPTS: int = 3
    # Exponential: delay = BACKOFF_BASE * 2 ** (attempts - 1), capped.
    JOB_BACKOFF_BASE_SECONDS: int = 30
    JOB_BACKOFF_MAX_SECONDS: int = 900
    # A running job writes a heartbeat on this interval. If one stops arriving
    # for JOB_STALE_AFTER_SECONDS the reaper assumes the worker died and
    # requeues the job. Keep the stale window several multiples of the
    # heartbeat interval so a slow document is not mistaken for a dead worker.
    JOB_HEARTBEAT_INTERVAL_SECONDS: float = 15.0
    JOB_STALE_AFTER_SECONDS: int = 300
    JOB_REAPER_INTERVAL_SECONDS: float = 60.0
    # Retain terminal jobs for this long so a failure can be inspected after
    # the fact, then delete them to keep the table small.
    JOB_RETENTION_HOURS: int = 168

    # ------------------------------------------------------------ generation
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "openai/gpt-oss-120b"
    GROQ_TEMPERATURE: float = 0.1
    GROQ_MAX_TOKENS: int = 1024
    GROQ_TIMEOUT_SECONDS: float = 60.0
    GROQ_MAX_RETRIES: int = 3
    # Server-Sent Events keep-alive. Proxies and load balancers close an idle
    # connection; a comment frame costs nothing and resets their timers while
    # the model is still thinking.
    SSE_KEEPALIVE_SECONDS: float = 15.0

    # Prompt assembly
    MAX_CONTEXT_CHARS: int = 12_000
    MAX_SNIPPET_CHARS: int = 2_000
    CHAT_HISTORY_TURNS: int = 6
    SESSION_TITLE_MAX_CHARS: int = 60
    NO_CONTEXT_ANSWER: str = (
        "I could not find anything in the indexed documents that answers this "
        "question. Try rephrasing it, or ingest a document that covers the topic."
    )


settings = Settings()
