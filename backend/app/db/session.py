"""SQLAlchemy engine and session factory. Owns database connectivity only."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.db.url import build_database_url

engine = create_engine(
    build_database_url(),
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_recycle=settings.DB_POOL_RECYCLE_SECONDS,
    pool_pre_ping=True,
    future=True,
)

SessionFactory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
