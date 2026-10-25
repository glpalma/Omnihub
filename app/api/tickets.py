import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import DB
from app.db.models import ConversationModel, TicketModel
from app.domain.models import TicketStatus
from app.domain.ticket_state import InvalidTransitionError, transition

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
async def transition_ticket(ticket_id: uuid.UUID, body: TransitionRequest, db: DB) -> TicketModel:
    result = await db.execute(select(TicketModel).where(TicketModel.id == ticket_id))
    ticket = result.scalar_one_or_none()
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")

    try:
        new_status = transition(TicketStatus(ticket.status), body.target_status)
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    ticket.status = new_status
    await db.commit()
    await db.refresh(ticket)
    return ticket
