"""
WhatsApp Cloud API webhook receiver.

Payload reference: https://developers.facebook.com/docs/whatsapp/cloud-api/webhooks/payload-examples
Only the fields required for ingestion are modelled; unknown fields are ignored.
"""
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import DB
from app.db.models import MessageModel

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


# ---- WhatsApp Cloud API payload schema (inbound) ----
# Only the minimum required fields; extras are stripped by pydantic.

class WATextBody(BaseModel):
    body: str


class WAMessage(BaseModel):
    id: str          # wamid — the external_message_id used for deduplication
    from_: str       # sender's phone number (field is "from" in JSON)
    timestamp: str
    type: str        # "text" | "image" | etc. — we only process "text" for now
    text: WATextBody | None = None

    model_config = {"populate_by_name": True}

    # pydantic alias so "from" in JSON → from_ in Python
    @classmethod
    def model_validate(cls, obj: Any, **kwargs: Any) -> "WAMessage":
        if isinstance(obj, dict) and "from" in obj:
            obj = {**obj, "from_": obj.pop("from")}
        return super().model_validate(obj, **kwargs)


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
                    continue

                arq_pool = request.app.state.arq_pool
                await arq_pool.enqueue_job(
                    "process_whatsapp_message",
                    {
                        "external_message_id": msg.id,
                        "sender": msg.from_,
                        "body": msg.text.body,
                        "timestamp": msg.timestamp,
                        "channel": "whatsapp",
                    },
                )

    return {"queued": True}
