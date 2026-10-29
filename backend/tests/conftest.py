"""Pytest fixtures for Family OS backend tests."""
from __future__ import annotations

import asyncio
import os
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

# Set test environment variables before importing app
os.environ["APP_ENV"] = "development"
os.environ["JWT_SECRET_KEY"] = "test-secret-key-that-is-at-least-32-chars-long"
os.environ["BOOTSTRAP_TOKEN"] = "test-bootstrap-token"
os.environ["LLM_PROVIDER"] = "mock"
os.environ["PRODUCT_PROVIDER"] = "development_catalogue"
os.environ["STT_PROVIDER"] = "disabled"
os.environ["TTS_PROVIDER"] = "disabled"

from unittest.mock import AsyncMock
from app.agents.adb_bridge import ADBBridge
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(autouse=True)
def mock_adb_for_all_tests(monkeypatch):
    """Ensure all automated tests run against simulated execution and do not gesture real USB devices."""
    monkeypatch.setattr(ADBBridge, "list_devices", AsyncMock(return_value=[]))


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def test_engine():
    engine = create_async_engine(
        TEST_DB_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def db_session(test_engine):
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture(scope="function")
async def client(db_session: AsyncSession):
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture(scope="function")
async def bootstrapped_admin(client: AsyncClient):
    """Create initial admin and family via bootstrap."""
    resp = await client.post(
        "/api/v1/auth/bootstrap",
        json={
            "bootstrap_token": "test-bootstrap-token",
            "email": "admin@family.local",
            "password": "Password123!",
            "display_name": "Family Admin",
            "family_name": "Test Family",
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


@pytest_asyncio.fixture(scope="function")
async def admin_headers(bootstrapped_admin):
    return {"Authorization": f"Bearer {bootstrapped_admin['access_token']}"}
