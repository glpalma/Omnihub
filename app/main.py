from contextlib import asynccontextmanager

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.tickets import router as tickets_router
from app.api.webhooks import router as webhooks_router
from app.core.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables if they don't exist.
    # ponytail: using create_all instead of Alembic — upgrade path is Alembic (Level 2)
    from app.db.models import Base
    from app.db.session import engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Shared ARQ connection pool used by webhook handlers to enqueue jobs
    app.state.arq_pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))

    yield

    await app.state.arq_pool.aclose()


app = FastAPI(
    title="Omnihub",
    description="Omnichannel messaging hub backend",
    lifespan=lifespan,
)

app.include_router(health_router)
app.include_router(tickets_router)
app.include_router(webhooks_router)
