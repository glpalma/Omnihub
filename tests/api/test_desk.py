import json
import uuid

from app.db.models import ConversationModel, MessageModel, TicketModel
from app.domain.models import Channel, TicketStatus
from app.events import CHANNEL


async def test_webchat_enqueues_inbound_job(client):
    c, pool = client
    resp = await c.post(
        "/webhooks/webchat",
        json={
            "session_id": "sess-carla",
            "message_id": "webchat.ONE",
            "text": "Oi pelo site",
        },
    )
    assert resp.status_code == 202
    job_name, job_data = pool.enqueue_job.call_args.args
    assert job_name == "process_inbound_message"
    assert job_data["channel"] == "webchat"
    assert job_data["sender"] == "sess-carla"
    assert job_data["body"] == "Oi pelo site"


async def test_webchat_duplicate_does_not_enqueue(client, db):
    c, pool = client
    conv = ConversationModel(
        id=uuid.uuid4(),
        channel=Channel.WEBCHAT,
        external_id="sess-carla",
    )
    db.add(conv)
    await db.flush()
    db.add(
        MessageModel(
            id=uuid.uuid4(),
            conversation_id=conv.id,
            external_message_id="webchat.ONE",
            channel=Channel.WEBCHAT,
            direction="inbound",
            body="Oi pelo site",
            sender="sess-carla",
        )
    )
    await db.commit()

    resp = await c.post(
        "/webhooks/webchat",
        json={
            "session_id": "sess-carla",
            "message_id": "webchat.ONE",
            "text": "Oi pelo site",
        },
    )
    assert resp.status_code == 202
    pool.enqueue_job.assert_not_awaited()
    pool.publish.assert_awaited()
    event = json.loads(pool.publish.await_args.args[1])
    assert pool.publish.await_args.args[0] == CHANNEL
    assert event["type"] == "webhook.duplicate"
    assert event["channel"] == "webchat"


async def test_reply_opens_new_ticket_and_stores_outbound(client, db):
    c, pool = client
    conv = ConversationModel(
        id=uuid.uuid4(),
        channel=Channel.WHATSAPP,
        external_id="+5511999990001",
    )
    db.add(conv)
    await db.flush()
    ticket = TicketModel(
        id=uuid.uuid4(),
        conversation_id=conv.id,
        status=TicketStatus.NEW,
    )
    db.add(ticket)
    await db.commit()

    resp = await c.post(
        f"/tickets/{ticket.id}/messages",
        json={"body": "Olá, já estou vendo seu pedido"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["direction"] == "outbound"
    assert body["sender"] == "atendente"
    assert body["body"] == "Olá, já estou vendo seu pedido"

    detail = await c.get(f"/tickets/{ticket.id}")
    assert detail.json()["status"] == "open"
    assert len(detail.json()["messages"]) == 1

    event = json.loads(pool.publish.await_args.args[1])
    assert event["type"] == "message.sent"
    assert event["ticket"]["status"] == "open"
    assert event["ticket"]["last_message"] == "Olá, já estou vendo seu pedido"
    assert event["ticket"]["message_count"] == 1


async def test_reply_rejects_closed_ticket(client, db):
    c, pool = client
    conv = ConversationModel(
        id=uuid.uuid4(),
        channel=Channel.WEBCHAT,
        external_id="sess-closed",
    )
    db.add(conv)
    await db.flush()
    ticket = TicketModel(
        id=uuid.uuid4(),
        conversation_id=conv.id,
        status=TicketStatus.CLOSED,
    )
    db.add(ticket)
    await db.commit()

    resp = await c.post(f"/tickets/{ticket.id}/messages", json={"body": "ainda estou aqui"})
    assert resp.status_code == 422
    pool.publish.assert_not_awaited()
