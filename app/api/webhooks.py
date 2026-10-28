"""
WhatsApp Cloud API webhook receiver.

Payload reference: https://developers.facebook.com/docs/whatsapp/cloud-api/webhooks/payload-examples
Only the fields required for ingestion are modelled; unknown fields are ignored.
"""
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import DB
from app.db.models import MessageModel
from app.events import publish

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


# ---- WhatsApp Cloud API payload schema (inbound) ----
# Only the minimum required fields; extras are stripped by pydantic.

class WATextBody(BaseModel):
    body: str


class WAMessage(BaseModel):
    id: str          # wamid — the external_message_id used for deduplication
    from_: str = Field(alias="from")  # "from" is a reserved keyword in Python
    timestamp: str
    type: str        # "text" | "image" | etc. — we only process "text" for now
    text: WATextBody | None = None

    model_config = {"populate_by_name": True}


class WAValue(BaseModel):
    messaging_product: str = ""
    messages: list[WAMessage] = []


class WAChange(BaseModel):
    value: WAValue
    field: str = ""


class WAEntry(BaseModel):
    id: str = ""
    changes: list[WAChange] = []


class WhatsAppWebhookPayload(BaseModel):
    object: str = ""
    entry: list[WAEntry] = []


# ---- endpoint ----

@router.post("/whatsapp", status_code=202)
async def receive_whatsapp(payload: WhatsAppWebhookPayload, db: DB, request: Request) -> dict:
    for entry in payload.entry:
        for change in entry.changes:
            for msg in change.value.messages:
                if msg.type != "text" or not msg.text:
                    continue  # ponytail: only text messages in Level 1; extend here for media

                # Idempotency check: skip if we've already enqueued/processed this wamid
                existing = await db.execute(
                    select(MessageModel).where(MessageModel.external_message_id == msg.id)
                )
                if existing.scalar_one_or_none() is not None:
                    # Already stored: do not enqueue a second job.
                    await publish(
                        request.app.state.arq_pool,
                        {
                            "type": "webhook.duplicate",
                            "channel": "whatsapp",
                            "external_message_id": msg.id,
                            "sender": msg.from_,
                        },
                    )
                    continue

                arq_pool = request.app.state.arq_pool
                await arq_pool.enqueue_job(
                    "process_inbound_message",
                    {
                        "external_message_id": msg.id,
                        "sender": msg.from_,
                        "body": msg.text.body,
                        "timestamp": msg.timestamp,
                        "channel": "whatsapp",
                    },
                )
                await publish(
                    arq_pool,
                    {
                        "type": "job.queued",
                        "channel": "whatsapp",
                        "external_message_id": msg.id,
                        "sender": msg.from_,
                        "body": msg.text.body,
                    },
                )

    return {"queued": True}


class WebchatPayload(BaseModel):
    session_id: str = Field(min_length=1)
    message_id: str = Field(min_length=1)
    text: str = Field(min_length=1)


@router.post("/webchat", status_code=202)
async def receive_webchat(payload: WebchatPayload, db: DB, request: Request) -> dict:
    """Site chat webhook. A different contract from WhatsApp, same queue."""
    existing = await db.execute(
        select(MessageModel).where(MessageModel.external_message_id == payload.message_id)
    )
    if existing.scalar_one_or_none() is not None:
        await publish(
            request.app.state.arq_pool,
            {
                "type": "webhook.duplicate",
                "channel": "webchat",
                "external_message_id": payload.message_id,
                "sender": payload.session_id,
            },
        )
        return {"queued": True}

    arq_pool = request.app.state.arq_pool
    await arq_pool.enqueue_job(
        "process_inbound_message",
        {
            "external_message_id": payload.message_id,
            "sender": payload.session_id,
            "body": payload.text,
            "timestamp": "",
            "channel": "webchat",
        },
    )
    await publish(
        arq_pool,
        {
            "type": "job.queued",
            "channel": "webchat",
            "external_message_id": payload.message_id,
            "sender": payload.session_id,
            "body": payload.text,
        },
    )
    return {"queued": True}
