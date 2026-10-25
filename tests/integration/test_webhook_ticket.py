"""
Integration tests for the webhook ingestion pipeline.

The HTTP tests mock the ARQ pool (no Redis needed).
The worker task tests call process_whatsapp_message() directly (no ARQ queue
needed), with AsyncSessionLocal patched to use the test SQLite engine.
"""
import uuid
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.models import ConversationModel, MessageModel, TicketModel
from app.workers.tasks import process_whatsapp_message

# Minimal valid WhatsApp Cloud API webhook payload
_WA_PAYLOAD = {
    "object": "whatsapp_business_account",
    "entry": [
        {
            "id": "123",
            "changes": [
                {
                    "field": "messages",
                    "value": {
                        "messaging_product": "whatsapp",
                        "messages": [
                            {
                                "id": "wamid.UNIQUE001",
                                "from": "+5511999990001",
                                "timestamp": "1700000000",
                                "type": "text",
                                "text": {"body": "Preciso de ajuda"},
                            }
                        ],
                    },
                }
            ],
        }
    ],
}


# ---- HTTP layer tests ----

async def test_webhook_returns_202(client):
    c, _ = client
    resp = await c.post("/webhooks/whatsapp", json=_WA_PAYLOAD)
    assert resp.status_code == 202
    assert resp.json() == {"queued": True}


async def test_webhook_enqueues_job_with_correct_data(client):
    c, mock_pool = client
    await c.post("/webhooks/whatsapp", json=_WA_PAYLOAD)
    mock_pool.enqueue_job.assert_called_once()
    job_name, job_data = mock_pool.enqueue_job.call_args.args
    assert job_name == "process_whatsapp_message"
    assert job_data["external_message_id"] == "wamid.UNIQUE001"
    assert job_data["sender"] == "+5511999990001"


async def test_webhook_idempotency_skips_duplicate_wamid(client, db):
    """Sending the same wamid twice must only enqueue one job."""
    c, mock_pool = client

    # First request — message is new, job is enqueued
    await c.post("/webhooks/whatsapp", json=_WA_PAYLOAD)
    assert mock_pool.enqueue_job.call_count == 1

    # Persist the message as if the worker already processed it
    conv = ConversationModel(id=uuid.uuid4(), channel="whatsapp", external_id="+5511999990001")
    db.add(conv)
    await db.flush()
    msg = MessageModel(
        id=uuid.uuid4(),
        conversation_id=conv.id,
        external_message_id="wamid.UNIQUE001",
        channel="whatsapp",
        direction="inbound",
        body="Preciso de ajuda",
        sender="+5511999990001",
    )
    db.add(msg)
    await db.commit()

    # Second request with the exact same wamid — must NOT enqueue again
    await c.post("/webhooks/whatsapp", json=_WA_PAYLOAD)
    assert mock_pool.enqueue_job.call_count == 1  # unchanged


# ---- Worker task tests (no HTTP, no ARQ queue) ----

@pytest.fixture
def patch_worker_db(test_engine):
    """Redirect the worker's AsyncSessionLocal to the test SQLite engine."""
    TestSession = async_sessionmaker(test_engine, expire_on_commit=False)
    with patch("app.workers.tasks.AsyncSessionLocal", TestSession):
        yield


async def test_worker_creates_conversation_message_ticket(db, test_engine, patch_worker_db):
    await process_whatsapp_message(
        ctx={},
        data={
            "external_message_id": "wamid.WORKER001",
            "sender": "+5511888880001",
            "body": "Olá, preciso de suporte",
            "timestamp": "1700001000",
            "channel": "whatsapp",
        },
    )

    msg = (await db.execute(
        select(MessageModel).where(MessageModel.external_message_id == "wamid.WORKER001")
    )).scalar_one()
    assert msg.body == "Olá, preciso de suporte"

    conv = (await db.execute(
        select(ConversationModel).where(ConversationModel.id == msg.conversation_id)
    )).scalar_one()
    assert conv.channel == "whatsapp"
    assert conv.external_id == "+5511888880001"

    ticket = (await db.execute(
        select(TicketModel).where(TicketModel.conversation_id == conv.id)
    )).scalar_one()
    assert ticket.status == "new"


async def test_worker_reuses_existing_open_ticket(db, test_engine, patch_worker_db):
    """A second message from the same sender must not open a second ticket."""
    for i, wamid in enumerate(["wamid.REUSE001", "wamid.REUSE002"]):
        await process_whatsapp_message(
            ctx={},
            data={
                "external_message_id": wamid,
                "sender": "+5511777770001",
                "body": f"Message {i}",
                "timestamp": str(1700002000 + i),
                "channel": "whatsapp",
            },
        )

    conv = (await db.execute(
        select(ConversationModel).where(ConversationModel.external_id == "+5511777770001")
    )).scalar_one()
    tickets = (await db.execute(
        select(TicketModel).where(TicketModel.conversation_id == conv.id)
    )).scalars().all()
    assert len(tickets) == 1


async def test_worker_idempotency_on_duplicate_wamid(db, test_engine, patch_worker_db):
    """Calling the task twice with the same wamid (ARQ retry) must not duplicate the message."""
    job_data = {
        "external_message_id": "wamid.IDEM001",
        "sender": "+5511666660001",
        "body": "Duplicate",
        "timestamp": "1700003000",
        "channel": "whatsapp",
    }
    await process_whatsapp_message(ctx={}, data=job_data)
    await process_whatsapp_message(ctx={}, data=job_data)  # simulate ARQ retry

    messages = (await db.execute(
        select(MessageModel).where(MessageModel.external_message_id == "wamid.IDEM001")
    )).scalars().all()
    assert len(messages) == 1
