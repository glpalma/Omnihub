import uuid

import pytest

from app.db.models import ConversationModel, TicketModel
from app.domain.models import Channel, TicketStatus


# ---- helpers ----

async def _seed_ticket(db, status=TicketStatus.NEW, channel=Channel.WHATSAPP) -> TicketModel:
    conv = ConversationModel(id=uuid.uuid4(), channel=channel, external_id=f"+55{uuid.uuid4().int % 10**11:011d}")
    db.add(conv)
    await db.flush()

    ticket = TicketModel(id=uuid.uuid4(), conversation_id=conv.id, status=status)
    db.add(ticket)
    await db.commit()
    return ticket


# ---- list endpoint ----

async def test_list_tickets_empty(client):
    c, _ = client
    resp = await c.get("/tickets")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_tickets_returns_existing(client, db):
    c, _ = client
    await _seed_ticket(db)
    resp = await c.get("/tickets")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


async def test_list_tickets_filter_by_status(client, db):
    c, _ = client
    await _seed_ticket(db, status=TicketStatus.NEW)
    await _seed_ticket(db, status=TicketStatus.OPEN)

    resp = await c.get("/tickets", params={"status": "open"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["status"] == "open"


async def test_list_tickets_filter_by_channel(client, db):
    c, _ = client
    await _seed_ticket(db, channel=Channel.WHATSAPP)
    await _seed_ticket(db, channel=Channel.WEBCHAT)

    resp = await c.get("/tickets", params={"channel": "whatsapp"})
    assert resp.status_code == 200
    # only the WhatsApp ticket should be returned
    assert len(resp.json()) == 1


# ---- detail endpoint ----

async def test_get_ticket_not_found(client):
    c, _ = client
    resp = await c.get(f"/tickets/{uuid.uuid4()}")
    assert resp.status_code == 404


async def test_get_ticket_returns_detail(client, db):
    c, _ = client
    ticket = await _seed_ticket(db)
    resp = await c.get(f"/tickets/{ticket.id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == str(ticket.id)
    assert "messages" in resp.json()


# ---- transition endpoint ----

async def test_transition_ticket_valid(client, db):
    c, _ = client
    ticket = await _seed_ticket(db, status=TicketStatus.NEW)
    resp = await c.post(f"/tickets/{ticket.id}/transition", json={"target_status": "open"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "open"


async def test_transition_ticket_invalid(client, db):
    c, _ = client
    ticket = await _seed_ticket(db, status=TicketStatus.NEW)
    # new → closed is not a valid transition
    resp = await c.post(f"/tickets/{ticket.id}/transition", json={"target_status": "closed"})
    assert resp.status_code == 422


async def test_transition_ticket_not_found(client):
    c, _ = client
    resp = await c.post(f"/tickets/{uuid.uuid4()}/transition", json={"target_status": "open"})
    assert resp.status_code == 404
