"""SQLAlchemy engine and session factory. Owns database connectivity only."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.db.url import build_database_url
from app.observability import db_timing

engine = create_engine(
    build_database_url(),
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_recycle=settings.DB_POOL_RECYCLE_SECONDS,
    pool_pre_ping=True,
    future=True,
)

# Every query issued through this engine is attributed to the request that
# issued it. Installed against the engine rather than inside the middleware
# because the engine is the only place that sees all of them — including
# queries from the ingestion worker, which no HTTP request ever touches.
db_timing.install(engine)

SessionFactory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
