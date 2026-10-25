from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.health import router as health_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # DB tables and ARQ pool are initialised in later steps
    yield


app = FastAPI(
    title="Omnihub",
    description="Omnichannel messaging hub backend",
    lifespan=lifespan,
)

app.include_router(health_router)
