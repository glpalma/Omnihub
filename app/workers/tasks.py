"""
ARQ tasks — background jobs that materialise inbound messages into the database.
"""
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.db.models import ConversationModel, MessageModel, TicketModel
from app.db.session import AsyncSessionLocal
from app.domain.models import Channel, TicketStatus
from app.events import publish, ticket_card


async def process_whatsapp_message(ctx: dict[str, Any], data: dict[str, Any]) -> None:
    """
    Materialise a WhatsApp inbound message into the DB and ensure a ticket exists.

    Steps:
      1. Upsert conversation (channel + external_id = sender's phone number).
      2. Insert message (skip silently on duplicate — second line of idempotency defence).
      3. Find the latest non-closed ticket for this conversation, or create one.
    """
    external_message_id: str = data["external_message_id"]
    sender: str = data["sender"]
    body: str = data["body"]
    channel = Channel(data.get("channel") or Channel.WHATSAPP)
    redis = ctx.get("redis")
    event: dict[str, Any] | None = None

    async with AsyncSessionLocal() as session:
        async with session.begin():
            # 1. Upsert conversation
            result = await session.execute(
                select(ConversationModel).where(
                    ConversationModel.channel == channel,
                    ConversationModel.external_id == sender,
                )
            )
            conversation = result.scalar_one_or_none()
            if conversation is None:
                conversation = ConversationModel(
                    id=uuid.uuid4(),
                    channel=channel,
                    external_id=sender,
                )
                session.add(conversation)
                await session.flush()  # get conversation.id before inserting message

            # 2. Insert message (idempotency: unique constraint on external_message_id)
            try:
                message = MessageModel(
                    id=uuid.uuid4(),
                    conversation_id=conversation.id,
                    external_message_id=external_message_id,
                    channel=channel,
                    direction="inbound",
                    body=body,
                    sender=sender,
                )
                session.add(message)
                await session.flush()
            except IntegrityError:
                # Already inserted by a concurrent worker or retry — safe to skip.
                # Second line of idempotency, behind the webhook's wamid check.
                await session.rollback()
                await publish(
                    redis,
                    {
                        "type": "message.duplicate",
                        "external_message_id": external_message_id,
                        "sender": sender,
                    },
                )
                return

            # 3. Ensure an active (non-closed, non-resolved) ticket exists
            ticket_result = await session.execute(
                select(TicketModel)
                .where(
                    TicketModel.conversation_id == conversation.id,
                    TicketModel.status.not_in([TicketStatus.CLOSED, TicketStatus.RESOLVED]),
                )
                .order_by(TicketModel.created_at.desc())
                .limit(1)
            )
            ticket = ticket_result.scalar_one_or_none()
            created = ticket is None
            if ticket is None:
                ticket = TicketModel(
                    id=uuid.uuid4(),
                    conversation_id=conversation.id,
                    status=TicketStatus.NEW,
                )
                session.add(ticket)
                await session.flush()

            message_count = await session.scalar(
                select(func.count())
                .select_from(MessageModel)
                .where(MessageModel.conversation_id == conversation.id)
            )
            await session.refresh(ticket)
            event = {
                "type": "ticket.created" if created else "message.appended",
                "external_message_id": external_message_id,
                "ticket": ticket_card(
                    ticket_id=ticket.id,
                    conversation_id=conversation.id,
                    status=ticket.status,
                    channel=channel,
                    external_id=sender,
                    sender=sender,
                    last_message=body,
                    last_external_message_id=external_message_id,
                    message_count=int(message_count or 0),
                    created_at=ticket.created_at,
                    updated_at=ticket.updated_at,
                ),
            }

    if event is not None:
        await publish(redis, event)


async def process_inbound_message(ctx: dict[str, Any], data: dict[str, Any]) -> None:
    """Same materialisation as WhatsApp, for any channel carried in the job."""
    await process_whatsapp_message(ctx, data)
