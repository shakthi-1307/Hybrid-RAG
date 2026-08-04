"""Public API contracts for registration, login, and the current user."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.config import settings


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=settings.PASSWORD_MIN_LENGTH)

    @field_validator("password")
    @classmethod
    def reject_passwords_bcrypt_would_truncate(cls, value: str) -> str:
        if len(value.encode("utf-8")) > settings.PASSWORD_MAX_BYTES:
            raise ValueError(
                f"Password must be at most {settings.PASSWORD_MAX_BYTES} bytes."
            )
        return value


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: EmailStr
    created_at: datetime
