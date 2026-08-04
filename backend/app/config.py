"""Single source of truth for every tunable constant in the application.

Rule: no module may hard-code a threshold, size, model name, or limit.
Everything is declared here once and imported as ``settings.<NAME>``.
"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
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
    LOG_FORMAT: str = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"

    # -------------------------------------------------------------- storage
    UPLOAD_DIR: Path = Path("/data/uploads")
    CHROMA_DIR: Path = Path("/data/chroma")
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

    # ---------------------------------------------------------- vector store
    CHROMA_COLLECTION_NAME: str = "document_chunks"
    CHROMA_DISTANCE_METRIC: str = "cosine"

    # ------------------------------------------------------------- retrieval
    VECTOR_CANDIDATE_COUNT: int = 40
    BM25_CANDIDATE_COUNT: int = 40
    BM25_K1: float = 1.5
    BM25_B: float = 0.75
    RRF_K: int = 60
    RRF_VECTOR_WEIGHT: float = 1.0
    RRF_BM25_WEIGHT: float = 0.8
    TOP_K: int = 6

    # ------------------------------------------------------------ generation
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.3-70b-versatile"
    GROQ_TEMPERATURE: float = 0.1
    GROQ_MAX_TOKENS: int = 1024
    GROQ_TIMEOUT_SECONDS: float = 60.0
    GROQ_MAX_RETRIES: int = 3

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
