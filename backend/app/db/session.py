"""Async SQLAlchemy engine and session factory.

A single module-level engine/sessionmaker pair is created from the
configured DATABASE_URL. FastAPI endpoints and scripts should use
`get_session` (as a dependency or async context manager) rather than
importing the sessionmaker directly, so that connection handling stays
consistent in one place.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

settings = get_settings()

engine: AsyncEngine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DB_ECHO,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields a request-scoped async session."""
    async with AsyncSessionLocal() as session:
        yield session


@asynccontextmanager
async def session_scope() -> AsyncGenerator[AsyncSession, None]:
    """Async context manager for scripts (outside of FastAPI's DI system).

    Commits on success, rolls back on error, always closes the session.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
