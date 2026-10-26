import json
import uuid

from app.db.models import ConversationModel, MessageModel, TicketModel
from app.domain.models import Channel, TicketStatus
from app.events import CHANNEL


async def test_board_returns_cards_and_transitions(client, db):
    c, _ = client
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
    await db.flush()
    db.add(
        MessageModel(
            id=uuid.uuid4(),
            conversation_id=conv.id,
            external_message_id="wamid.BOARD001",
            channel=Channel.WHATSAPP,
            direction="inbound",
            body="Preciso de ajuda",
            sender="+5511999990001",
        )
    )
    await db.commit()

    resp = await c.get("/board")
    assert resp.status_code == 200
    body = resp.json()
    assert body["transitions"]["new"] == ["open"]
    assert body["transitions"]["closed"] == []
    assert len(body["tickets"]) == 1
    card = body["tickets"][0]
    assert card["id"] == str(ticket.id)
    assert card["status"] == "new"
    assert card["channel"] == "whatsapp"
    assert card["external_id"] == "+5511999990001"
    assert card["last_message"] == "Preciso de ajuda"
    assert card["last_external_message_id"] == "wamid.BOARD001"
    assert card["message_count"] == 1


async def test_transition_publishes_event(client, db):
    c, pool = client
    conv = ConversationModel(
        id=uuid.uuid4(),
        channel=Channel.WHATSAPP,
        external_id="+5511888880002",
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
        f"/tickets/{ticket.id}/transition",
        json={"target_status": "open"},
    )
    assert resp.status_code == 200

    pool.publish.assert_awaited()
    channel, raw = pool.publish.await_args.args
    event = json.loads(raw)
    assert channel == CHANNEL
    assert event["type"] == "ticket.transitioned"
    assert event["from_status"] == "new"
    assert event["to_status"] == "open"
    assert event["ticket"]["status"] == "open"
    assert event["ticket"]["external_id"] == "+5511888880002"


async def test_invalid_transition_does_not_publish(client, db):
    c, pool = client
    conv = ConversationModel(
        id=uuid.uuid4(),
        channel=Channel.WHATSAPP,
        external_id="+5511777770002",
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
        f"/tickets/{ticket.id}/transition",
        json={"target_status": "closed"},
    )
    assert resp.status_code == 422
    pool.publish.assert_not_awaited()
