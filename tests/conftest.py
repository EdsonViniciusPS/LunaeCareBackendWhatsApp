import asyncio
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base, get_db
from app.main import app
from app.providers import get_whatsapp_provider
from app.providers.evolution import EvolutionProvider

# Banco de dados de teste SQLite em memória
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False}
)

TestingSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False
)


@pytest_asyncio.fixture(scope="function")
async def db_session():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with TestingSessionLocal() as session:
        yield session

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(scope="function")
async def mock_provider():
    return EvolutionProvider(mock_mode=True)


@pytest_asyncio.fixture(scope="function")
async def client(db_session: AsyncSession, mock_provider: EvolutionProvider):
    async def override_get_db():
        yield db_session

    def override_get_provider():
        return mock_provider

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_whatsapp_provider] = override_get_provider

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c

    app.dependency_overrides.clear()
