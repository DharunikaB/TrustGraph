"""Shared pytest fixtures.

Tests use an in-memory SQLite database rather than PostgreSQL so the
suite runs anywhere without a live database -- the ORM models are
written to be portable (string UUID PKs, standard column types), so
this is a meaningful test of the schema itself, not just a mock.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app import models  # noqa: F401  -- registers all models on Base.metadata


@pytest_asyncio.fixture
async def async_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    # SQLite doesn't enforce FK constraints unless explicitly turned on.
    from sqlalchemy import event

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_fk(dbapi_connection, _):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()
