"""
Shared pytest fixtures.

Every test gets a fresh in-memory SQLite database (via aiosqlite) — no
running infrastructure required.  The lifespan does not run in ASGI transport
mode, so we set app.state.arq_pool to an AsyncMock directly.
"""
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.models import Base
from app.db.session import get_db


TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
async def test_engine():
    """Fresh in-memory SQLite database per test (fast, fully isolated)."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def db(test_engine):
    """Async session wired to the per-test SQLite engine."""
    TestSession = async_sessionmaker(test_engine, expire_on_commit=False)
    async with TestSession() as session:
        yield session


@pytest.fixture
async def client(db):
    """
    HTTP test client with:
    - DB dependency overridden to the per-test SQLite session
    - app.state.arq_pool set to an AsyncMock (no Redis; inspect enqueue calls)

    Note: ASGITransport does not trigger the ASGI lifespan, so we set state
    attributes manually instead of relying on the startup event.
    """
    from app.main import app

    mock_pool = AsyncMock()
    app.state.arq_pool = mock_pool

    async def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c, mock_pool

    app.dependency_overrides.clear()
    # Reset state so other test sessions start clean
    del app.state.arq_pool
