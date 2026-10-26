from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import DB
from app.db.models import ConversationModel, TicketModel
from app.domain.models import TicketStatus
from app.domain.ticket_state import VALID_TRANSITIONS
from app.events import card_from_ticket

router = APIRouter(tags=["board"])

# Column order used to list legal targets the same way the board shows them.
_STATUS_ORDER = list(TicketStatus)


class BoardCard(BaseModel):
    id: str
    conversation_id: str
    status: str
    channel: str | None
    external_id: str | None
    sender: str | None
    last_message: str | None
    last_external_message_id: str | None
    message_count: int
    created_at: str | None
    updated_at: str | None


class BoardOut(BaseModel):
    tickets: list[BoardCard]
    transitions: dict[str, list[str]]


def transition_map() -> dict[str, list[str]]:
    return {
        status.value: [target.value for target in _STATUS_ORDER if target in allowed]
        for status, allowed in VALID_TRANSITIONS.items()
    }


@router.get("/board", response_model=BoardOut)
async def get_board(db: DB) -> dict:
    """Snapshot the kanban uses on load and whenever the SSE stream reconnects."""
    stmt = (
        select(TicketModel)
        .options(selectinload(TicketModel.conversation).selectinload(ConversationModel.messages))
        .order_by(TicketModel.updated_at.desc())
    )
    result = await db.execute(stmt)
    tickets = result.scalars().unique().all()
    return {
        "tickets": [card_from_ticket(ticket) for ticket in tickets],
        "transitions": transition_map(),
    }
