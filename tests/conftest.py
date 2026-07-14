"""Shared pytest fixtures for unit and integration tests."""
from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from bot.database.base import Base
import bot.database.models  # noqa: F401 — registers all models


TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture(scope="session")
async def engine():
    eng = create_async_engine(TEST_DB_URL, echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session(engine):
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as sess:
        yield sess
        await sess.rollback()


@pytest_asyncio.fixture
async def sample_user(session: AsyncSession):
    from bot.services.user_service import UserService
    svc = UserService(session)
    user, _ = await svc.get_or_create(
        telegram_id=123456789,
        first_name="Test",
        username="testuser",
    )
    await session.commit()
    return user
