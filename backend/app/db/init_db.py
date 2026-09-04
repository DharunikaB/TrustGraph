"""Table creation helper.

M1 uses `Base.metadata.create_all` directly (no Alembic migrations
yet) since the schema is still being established. A migration tool can
be introduced in a later milestone once the schema stabilizes.
"""

import asyncio
import logging

from app.db.base import Base
from app.db.session import engine

# Import the models package so every model class registers itself on
# Base.metadata before create_all() runs.
from app import models  # noqa: F401

logger = logging.getLogger(__name__)


async def init_models() -> None:
    """Create all tables that don't already exist."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created (or already present).")


async def drop_models() -> None:
    """Drop all tables. Intended for local development / test resets only."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    logger.info("Database tables dropped.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(init_models())
