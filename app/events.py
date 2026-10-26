"""Live events for the Level 1 board.

The API and the ARQ worker are separate processes. Both publish JSON on one
Redis channel; the SSE endpoint subscribes and forwards those messages to
the browser.
"""
import json
import logging
from datetime import datetime
from typing import Any

from app.db.models import TicketModel

log = logging.getLogger(__name__)

CHANNEL = "omnihub:events"


def _value(value: Any) -> str | None:
    if value is None:
        return None
    return value.value if hasattr(value, "value") else str(value)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def ticket_card(
    *,
    ticket_id: Any,
    conversation_id: Any,
    status: Any,
    channel: Any,
    external_id: str | None,
    sender: str | None,
    last_message: str | None,
    last_external_message_id: str | None,
    message_count: int,
    created_at: datetime | None,
    updated_at: datetime | None,
) -> dict[str, Any]:
    """Shape shared by GET /board and every ticket event on the stream."""
    return {
        "id": str(ticket_id),
        "conversation_id": str(conversation_id),
        "status": _value(status),
        "channel": _value(channel),
        "external_id": external_id,
        "sender": sender,
        "last_message": last_message,
        "last_external_message_id": last_external_message_id,
        "message_count": message_count,
        "created_at": _iso(created_at),
        "updated_at": _iso(updated_at),
    }


def card_from_ticket(ticket: TicketModel) -> dict[str, Any]:
    conversation = ticket.conversation
    messages = []
    if conversation is not None and conversation.messages:
        messages = sorted(
            conversation.messages,
            key=lambda item: item.created_at or datetime.min,
        )
    last = messages[-1] if messages else None
    external_id = conversation.external_id if conversation is not None else None
    return ticket_card(
        ticket_id=ticket.id,
        conversation_id=ticket.conversation_id,
        status=ticket.status,
        channel=conversation.channel if conversation is not None else None,
        external_id=external_id,
        sender=last.sender if last is not None else external_id,
        last_message=last.body if last is not None else None,
        last_external_message_id=(
            last.external_message_id if last is not None else None
        ),
        message_count=len(messages),
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
    )


async def publish(redis: Any, event: dict[str, Any]) -> None:
    """Publish one event. A missing client or a blip must not fail the job."""
    if redis is None:
        return
    payload = dict(event)
    payload.setdefault("at", datetime.now().astimezone().isoformat())
    try:
        await redis.publish(CHANNEL, json.dumps(payload))
    except Exception:
        log.warning("failed to publish %s", payload.get("type"), exc_info=True)
