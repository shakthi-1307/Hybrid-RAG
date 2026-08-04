"""Domain exceptions.

Every class here is raised somewhere in the codebase and mapped to an HTTP
status by the single handler registered in ``app.main``.
"""

from __future__ import annotations


class AppError(Exception):
    """Base class for expected, user-facing failures."""

    status_code: int = 400

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class UnsupportedFormatError(AppError):
    status_code = 415


class DocumentTooLargeError(AppError):
    status_code = 413


class EmptyDocumentError(AppError):
    status_code = 422


class AuthenticationError(AppError):
    status_code = 401


class EmailAlreadyRegisteredError(AppError):
    status_code = 409


class ResourceNotFoundError(AppError):
    status_code = 404


class GenerationError(AppError):
    status_code = 502
