from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from uuid import UUID


class Channel(str, Enum):
    WHATSAPP = "whatsapp"
    WEBCHAT = "webchat"


class TicketStatus(str, Enum):
    NEW = "new"
    OPEN = "open"
    WAITING_CUSTOMER = "waiting_customer"
    RESOLVED = "resolved"
    CLOSED = "closed"


@dataclass
class Message:
    id: UUID
    conversation_id: UUID
    external_message_id: str
    channel: Channel
    direction: str  # "inbound" | "outbound"
    body: str
    sender: str  # phone number or session identifier
    created_at: datetime


@dataclass
class Conversation:
    id: UUID
    channel: Channel
    external_id: str  # phone number for WhatsApp, session_id for webchat
    created_at: datetime


@dataclass
class Ticket:
    id: UUID
    conversation_id: UUID
    status: TicketStatus
    created_at: datetime
    updated_at: datetime
    agent_id: UUID | None = None


@dataclass
class Agent:
    id: UUID
    name: str
    email: str
    created_at: datetime = field(default_factory=datetime.utcnow)
