"""Shared column mixins used across ORM models."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column


def _new_uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UUIDPrimaryKeyMixin:
    """Adds a string UUID primary key.

    Stored as a plain string (rather than the Postgres-specific UUID
    type) so the same model definitions work against PostgreSQL in
    production and SQLite in fast local/unit tests.
    """

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_new_uuid
    )


class TimestampMixin:
    """Adds a `created_at` column defaulting to current UTC time."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
