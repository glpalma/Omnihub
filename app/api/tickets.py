import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import DB
from app.db.models import ConversationModel, MessageModel, TicketModel
from app.domain.models import Channel, TicketStatus
from app.domain.ticket_state import InvalidTransitionError, transition
from app.events import card_from_ticket, publish

router = APIRouter(prefix="/tickets", tags=["tickets"])


# ---- response schemas ----

class MessageOut(BaseModel):
    id: uuid.UUID
    external_message_id: str
    channel: str
    direction: str
    body: str
    sender: str
    created_at: Any

    model_config = {"from_attributes": True}


class TicketOut(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    status: str
    agent_id: uuid.UUID | None
    created_at: Any
    updated_at: Any

    model_config = {"from_attributes": True}


class TicketDetailOut(TicketOut):
    """Ticket with the full message history from its conversation."""
    messages: list[MessageOut] = []


class TransitionRequest(BaseModel):
    target_status: TicketStatus


class AgentReply(BaseModel):
    body: str


# ---- endpoints ----

@router.get("", response_model=list[TicketOut])
async def list_tickets(
    db: DB,
    status: TicketStatus | None = Query(None),
    agent_id: uuid.UUID | None = Query(None),
    channel: str | None = Query(None),
) -> list[TicketModel]:
    stmt = select(TicketModel)

    if status:
        stmt = stmt.where(TicketModel.status == status)
    if agent_id:
        stmt = stmt.where(TicketModel.agent_id == agent_id)
    if channel:
        stmt = stmt.join(ConversationModel).where(ConversationModel.channel == channel)

    result = await db.execute(stmt.order_by(TicketModel.created_at.desc()))
    return list(result.scalars().all())


@router.get("/{ticket_id}", response_model=TicketDetailOut)
async def get_ticket(ticket_id: uuid.UUID, db: DB) -> Any:
    stmt = (
        select(TicketModel)
        .where(TicketModel.id == ticket_id)
        .options(
            selectinload(TicketModel.conversation).selectinload(ConversationModel.messages)
        )
    )
    result = await db.execute(stmt)
    ticket = result.scalar_one_or_none()
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")

    # Flatten messages from the conversation into the response
    return {
        "id": ticket.id,
        "conversation_id": ticket.conversation_id,
        "status": ticket.status,
        "agent_id": ticket.agent_id,
        "created_at": ticket.created_at,
        "updated_at": ticket.updated_at,
        "messages": ticket.conversation.messages if ticket.conversation else [],
    }


@router.post("/{ticket_id}/transition", response_model=TicketOut)
async def transition_ticket(
    ticket_id: uuid.UUID,
    body: TransitionRequest,
    request: Request,
    db: DB,
) -> TicketModel:
    stmt = (
        select(TicketModel)
        .where(TicketModel.id == ticket_id)
        .options(selectinload(TicketModel.conversation).selectinload(ConversationModel.messages))
    )
    result = await db.execute(stmt)
    ticket = result.scalar_one_or_none()
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")

    try:
        new_status = transition(TicketStatus(ticket.status), body.target_status)
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    status = ticket.status
    from_status = status.value if hasattr(status, "value") else str(status)
    card = card_from_ticket(ticket)
    card["status"] = new_status.value
    ticket.status = new_status
    await db.commit()
    await db.refresh(ticket)
    updated_at = ticket.updated_at
    card["updated_at"] = updated_at.isoformat() if updated_at else card["updated_at"]
    await publish(
        request.app.state.arq_pool,
        {
            "type": "ticket.transitioned",
            "from_status": from_status,
            "to_status": new_status.value,
            "ticket": card,
        },
    )
    return ticket


def _as_status(value: Any) -> TicketStatus:
    if isinstance(value, TicketStatus):
        return value
    raw = value.value if hasattr(value, "value") else value
    return TicketStatus(raw)


def _as_channel(value: Any) -> Channel:
    if isinstance(value, Channel):
        return value
    raw = value.value if hasattr(value, "value") else value
    return Channel(raw)


@router.post("/{ticket_id}/messages", response_model=MessageOut)
async def reply_to_ticket(
    ticket_id: uuid.UUID,
    body: AgentReply,
    request: Request,
    db: DB,
) -> MessageModel:
    """Store the attendant's reply. Speaking on a new ticket also opens it."""
    text = body.body.strip()
    if not text:
        raise HTTPException(status_code=422, detail="A resposta não pode ser vazia")

    stmt = (
        select(TicketModel)
        .where(TicketModel.id == ticket_id)
        .options(selectinload(TicketModel.conversation).selectinload(ConversationModel.messages))
    )
    result = await db.execute(stmt)
    ticket = result.scalar_one_or_none()
    if ticket is None or ticket.conversation is None:
        raise HTTPException(status_code=404, detail="Ticket not found")

    current = _as_status(ticket.status)
    if current is TicketStatus.CLOSED:
        raise HTTPException(status_code=422, detail="Ticket fechado não recebe resposta")
    if current is not TicketStatus.OPEN:
        ticket.status = transition(current, TicketStatus.OPEN)

    message = MessageModel(
        id=uuid.uuid4(),
        conversation_id=ticket.conversation_id,
        external_message_id=f"agent.{uuid.uuid4()}",
        channel=_as_channel(ticket.conversation.channel),
        direction="outbound",
        body=text,
        sender="atendente",
    )
    ticket.updated_at = datetime.now(timezone.utc)
    db.add(message)
    await db.commit()
    await db.refresh(message)
    db.expire(ticket.conversation, ["messages"])

    reloaded = await db.execute(stmt)
    ticket = reloaded.scalar_one()
    await publish(
        request.app.state.arq_pool,
        {
            "type": "message.sent",
            "external_message_id": message.external_message_id,
            "ticket": card_from_ticket(ticket),
        },
    )
    await db.refresh(message)
    return message
