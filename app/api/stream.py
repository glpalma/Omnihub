"""Server-Sent Events.

Each browser gets its own Redis connection. A pub/sub subscription occupies
the connection it runs on, so this must not reuse the ARQ pool — that pool
has to stay free to enqueue jobs.
"""
from collections.abc import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from redis.asyncio import Redis

from app.core.config import settings
from app.events import CHANNEL

router = APIRouter(tags=["events"])

_KEEPALIVE_SECONDS = 15.0


@router.get("/events")
async def stream_events(request: Request) -> StreamingResponse:
    async def generate() -> AsyncIterator[str]:
        client = Redis.from_url(settings.redis_url, decode_responses=True)
        pubsub = client.pubsub()
        await pubsub.subscribe(CHANNEL)
        try:
            yield 'data: {"type":"hello"}\n\n'
            while True:
                if await request.is_disconnected():
                    break
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=_KEEPALIVE_SECONDS,
                )
                if message is None:
                    yield ": keepalive\n\n"
                    continue
                if message.get("type") != "message":
                    continue
                yield f"data: {message['data']}\n\n"
        finally:
            await pubsub.unsubscribe(CHANNEL)
            await pubsub.aclose()
            await client.aclose()

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
