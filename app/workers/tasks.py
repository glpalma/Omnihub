"""
ARQ tasks — background jobs that materialise inbound messages into the database.
"""
from datetime import datetime, timedelta, timezone
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.db.models import ConversationModel, MessageModel, TicketModel
from app.db.session import AsyncSessionLocal
from app.domain.models import Channel, TicketStatus
from app.events import card_from_ticket, publish, ticket_card
from app.services.bot_agent import BotAgentService
from app.services.whatsapp_sender import WhatsAppSendError, WhatsAppSenderService


async def process_inbound_message(ctx: dict[str, Any], data: dict[str, Any]) -> None:
    """
    Materialise an inbound message into the DB and ensure a ticket exists.

    Works for every channel — the channel is carried in data["channel"].

    Steps:
      1. Upsert conversation (channel + external_id).
      2. Insert message (idempotency: skip on duplicate external_message_id).
      3. Find or create an active ticket; new tickets start as BOT.
      4. If the ticket was just created, enqueue run_bot_turn.
    """
    external_message_id: str = data["external_message_id"]
    sender: str = data["sender"]
    body: str = data["body"]
    channel = Channel(data.get("channel") or Channel.UNKNOWN)
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
                    status=TicketStatus.BOT,
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
        
        ticket_still_with_bot = not created and TicketStatus(ticket.status) is TicketStatus.BOT
        if (created or ticket_still_with_bot) and redis is not None:
            await redis.enqueue_job(
            "run_bot_turn",
            {
                "ticket_id": str(ticket.id),
                "conversation_id": str(conversation.id),
                "channel": channel.value,
                "sender": sender,
            },
            _job_id=f"bot_turn_{ticket.id}",   # ID determinístico por ticket
            _defer_by=timedelta(seconds=3),    # pequeno delay para evitar colisões
        )


_bot_agent = BotAgentService()
_wa_sender = WhatsAppSenderService()

async def run_bot_turn(ctx: dict[str, Any], data: dict[str, Any]) -> None:
    """
    Executa um turno do bot para o ticket indicado.

    Recebe:
        data["ticket_id"]       — UUID do ticket
        data["conversation_id"] — UUID da conversa
        data["channel"]         — "whatsapp" | "webchat"
        data["sender"]          — número/session_id do cliente

    O job é idempotente: se o ticket já saiu do status BOT (transição feita
    por execução anterior ou por um agente humano), encerra silenciosamente.
    """
    ticket_id = uuid.UUID(data["ticket_id"])
    conversation_id = uuid.UUID(data["conversation_id"])
    channel = Channel(data["channel"])
    sender: str = data["sender"]
    redis = ctx.get("redis")

    # -------------------------------------------------------------------------
    # 1. Carregar ticket e verificar idempotência
    # -------------------------------------------------------------------------
    async with AsyncSessionLocal() as session:
        ticket_result = await session.execute(
            select(TicketModel).where(TicketModel.id == ticket_id)
        )
        ticket = ticket_result.scalar_one_or_none()

        if ticket is None:
            return  # ticket deletado — não há o que fazer

        current_status = TicketStatus(ticket.status)
        if current_status is not TicketStatus.BOT:
            # Já foi transicionado por execução anterior ou agente humano.
            return

        # -------------------------------------------------------------------------
        # 2. Carregar histórico completo da conversa
        # -------------------------------------------------------------------------
        messages_result = await session.execute(
            select(MessageModel)
            .where(MessageModel.conversation_id == conversation_id)
            .order_by(MessageModel.created_at.asc())
        )
        messages = list(messages_result.scalars().all())

    # -------------------------------------------------------------------------
    # 3. Chamar o BotAgentService (fora da sessão — evita hold de conexão DB)
    # -------------------------------------------------------------------------
    decision = await _bot_agent.run_turn(messages)

    # -------------------------------------------------------------------------
    # 4. Persistir resposta e aplicar transição de status
    # -------------------------------------------------------------------------
    async with AsyncSessionLocal() as session:
        async with session.begin():
            # Recarregar ticket dentro desta sessão para aplicar UPDATE
            ticket_result = await session.execute(
                select(TicketModel)
                .where(TicketModel.id == ticket_id)
                .options(
                    selectinload(TicketModel.conversation).selectinload(
                        ConversationModel.messages
                    )
                )
            )
            ticket = ticket_result.scalar_one_or_none()
            if ticket is None:
                return

            # Idempotência dupla: confirmar status ainda é BOT antes de alterar
            if TicketStatus(ticket.status) is not TicketStatus.BOT:
                return

            # Persistir mensagem de saída do bot
            outbound = MessageModel(
                id=uuid.uuid4(),
                conversation_id=conversation_id,
                external_message_id=f"bot.{uuid.uuid4()}",
                channel=channel,
                direction="outbound",
                body=decision.reply_text,
                sender="bot",
                created_at=datetime.now(timezone.utc),
            )
            session.add(outbound)

            # Aplicar transição de status
            if decision.action == "resolved":
                ticket.status = TicketStatus.RESOLVED
            elif decision.action == "escalate":
                ticket.status = TicketStatus.NEW

            ticket.updated_at = datetime.now(timezone.utc)
            await session.flush()
            await session.refresh(outbound)

            # A coleção já estava carregada antes do INSERT. Sem este append,
            # o card publica message_count e last_message velhos, e o chat
            # aberto não refaz o GET /tickets.
            conversation = ticket.conversation
            if conversation is not None and outbound not in conversation.messages:
                conversation.messages.append(outbound)

            card = card_from_ticket(ticket)
            status_value = (
                ticket.status.value if hasattr(ticket.status, "value") else str(ticket.status)
            )
            external_message_id = outbound.external_message_id

    # -------------------------------------------------------------------------
    # 5. Enviar mensagem ao cliente pelo canal correto
    # -------------------------------------------------------------------------
    if channel is Channel.WHATSAPP:
        try:
            await _wa_sender.send(to=sender, text=decision.reply_text)
        except WhatsAppSendError:
            # Não interrompe o fluxo: ticket já foi transicionado no banco.
            pass

    # -------------------------------------------------------------------------
    # 6. Publicar evento no Redis (alimenta SSE do board e webchat)
    # -------------------------------------------------------------------------
    await publish(
        redis,
        {
            "type": "message.sent",
            "external_message_id": external_message_id,
            "ticket": card,
        },
    )
    if decision.action != "reply":
        await publish(
            redis,
            {
                "type": "ticket.transitioned",
                "from_status": TicketStatus.BOT.value,
                "to_status": status_value,
                "ticket": card,
            },
        )