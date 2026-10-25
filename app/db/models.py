import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.domain.models import Channel, TicketStatus


class Base(DeclarativeBase):
    pass


class ConversationModel(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    channel: Mapped[str] = mapped_column(Enum(Channel, name="channel_enum"), nullable=False)
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    messages: Mapped[list["MessageModel"]] = relationship("MessageModel", back_populates="conversation")
    tickets: Mapped[list["TicketModel"]] = relationship("TicketModel", back_populates="conversation")

    __table_args__ = (
        UniqueConstraint("channel", "external_id", name="uq_conversation_channel_external_id"),
    )


class MessageModel(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    external_message_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    channel: Mapped[str] = mapped_column(Enum(Channel, name="channel_enum"), nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)  # inbound | outbound
    body: Mapped[str] = mapped_column(Text, nullable=False)
    sender: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    conversation: Mapped["ConversationModel"] = relationship("ConversationModel", back_populates="messages")


class TicketModel(Base):
    __tablename__ = "tickets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        Enum(TicketStatus, name="ticket_status_enum"), nullable=False, default=TicketStatus.NEW
    )
    agent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    conversation: Mapped["ConversationModel"] = relationship("ConversationModel", back_populates="tickets")
