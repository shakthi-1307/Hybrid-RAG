"""Application assembly. Wires configuration, middleware, routers, and lifespan."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import auth, chat, documents, health
from app.config import settings
from app.errors import AppError
from app.observability.context import get_request_id
from app.observability.logging_config import configure_logging
from app.observability.middleware import RequestContextMiddleware
from app.startup_checks import verify_configuration

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    verify_configuration()
    settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    # No index to build here any more. The lexical index is a generated column
    # and the vector index is an HNSW index, both maintained by Postgres as
    # rows are written — so startup no longer has to read the whole corpus,
    # and a second API process is no longer a second, divergent copy of it.
    logger.info("%s %s ready", settings.APP_NAME, settings.APP_VERSION)
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # Without this the browser hides the header from JavaScript, so the UI
    # cannot show the user an id to quote in a bug report.
    expose_headers=[settings.REQUEST_ID_HEADER],
)

# Registered LAST so it ends up OUTERMOST. add_middleware inserts at the front
# of the list, and Starlette wraps that list from the end, so the final
# registration is the first to see a request. The request id has to exist
# before anything else can log against it — including requests CORS rejects
# and exceptions raised inside another middleware.
app.add_middleware(RequestContextMiddleware)


@app.exception_handler(AppError)
async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message, "request_id": get_request_id()},
        headers=exc.headers,
    )


@app.exception_handler(Exception)
async def handle_unexpected_error(_: Request, exc: Exception) -> JSONResponse:
    """Turn an unhandled exception into a response that can be traced.

    The message is deliberately generic — an internal error string can leak
    schema details or file paths. The request id is not, and it is the thing
    that lets a support conversation find the stack trace this logged.
    """
    logger.exception("Unhandled exception", exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "An unexpected error occurred.",
            "request_id": get_request_id(),
        },
    )


app.include_router(health.router, prefix=settings.API_PREFIX)
app.include_router(auth.router, prefix=settings.API_PREFIX)
app.include_router(documents.router, prefix=settings.API_PREFIX)
app.include_router(chat.router, prefix=settings.API_PREFIX)
