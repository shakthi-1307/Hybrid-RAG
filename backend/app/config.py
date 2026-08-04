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
    DATABASE_URL: str = "postgresql+psycopg://rag:rag@postgres:5432/rag"
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_RECYCLE_SECONDS: int = 1800

    # ------------------------------------------------------------------ auth
    # Override JWT_SECRET_KEY in every deployment. The default exists so the
    # stack boots locally, and is useless to an attacker who cannot read .env.
    JWT_SECRET_KEY: str = "Shakthi@777"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRY_MINUTES: int = 60 * 24 * 7
    AUTH_COOKIE_NAME: str = "rag_session"
    AUTH_COOKIE_SECURE: bool = True  # set True behind HTTPS
    AUTH_COOKIE_SAMESITE: str = "lax"
    BCRYPT_ROUNDS: int = 12
    PASSWORD_MIN_LENGTH: int = 10
    # bcrypt silently ignores input past 72 bytes, so reject it instead.
    PASSWORD_MAX_BYTES: int = 72

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
