from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.tickets import router as tickets_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create all tables if they don't exist yet.
    # ponytail: using create_all instead of Alembic migrations — upgrade path is Alembic (Level 2)
    from app.db.models import Base
    from app.db.session import engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield


app = FastAPI(
    title="Omnihub",
    description="Omnichannel messaging hub backend",
    lifespan=lifespan,
)

app.include_router(health_router)
app.include_router(tickets_router)
