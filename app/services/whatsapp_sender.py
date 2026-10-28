"""
WhatsAppSenderService — envia mensagens de texto para o cliente via WhatsApp Cloud API.

Referência da API:
  https://developers.facebook.com/docs/whatsapp/cloud-api/messages/text-messages
"""
from __future__ import annotations

import logging

import httpx

from app.core.config import settings

log = logging.getLogger(__name__)

# Versão da Graph API usada. Atualizar aqui muda para todos os envios.
_GRAPH_API_VERSION = "v19.0"


class WhatsAppSendError(Exception):
    """Levantado quando a Meta retorna status HTTP != 2xx."""


class WhatsAppSenderService:
    """
    Envia uma mensagem de texto simples para um número WhatsApp.

    Instanciar uma vez e reutilizar dentro do worker (o httpx.AsyncClient
    faz pooling de conexões internamente).
    """

    def __init__(self) -> None:
        self._phone_number_id = settings.wa_phone_number_id
        self._token = settings.wa_token
        self._base_url = (
            f"https://graph.facebook.com/{_GRAPH_API_VERSION}"
            f"/{self._phone_number_id}/messages"
        )

    async def send(self, to: str, text: str) -> None:
        """
        Envia *text* para o número *to* (formato E.164, ex.: "+5511999990000").

        Levanta WhatsAppSendError se a API retornar erro. O worker decide
        se propaga ou absorve a exceção.
        """
        if not self._phone_number_id or not self._token:
            log.warning(
                "WhatsAppSenderService: WA_PHONE_NUMBER_ID ou WA_TOKEN não configurados. "
                "Mensagem para %s não enviada.",
                to,
            )
            return

        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": text},
        }
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(self._base_url, json=payload, headers=headers)

        if not response.is_success:
            log.error(
                "WhatsAppSenderService: falha ao enviar para %s — HTTP %s: %s",
                to,
                response.status_code,
                response.text[:500],
            )
            raise WhatsAppSendError(
                f"Meta API retornou {response.status_code}: {response.text[:200]}"
            )

        log.info("WhatsAppSenderService: mensagem enviada para %s", to)