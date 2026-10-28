"""
BotAgentService — chama a Featherless AI e devolve uma BotDecision tipada.

A Featherless AI expõe uma API 100% compatível com a OpenAI, então usamos
o SDK `openai` apontando para o base_url deles.

O serviço não tem efeitos colaterais: não lê nem escreve no banco, não publica
eventos. Toda a orquestração fica no worker run_bot_turn (slice 04).
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Literal

from openai import AsyncOpenAI

from app.core.config import settings
from app.db.models import MessageModel

log = logging.getLogger(__name__)

_FEATHERLESS_BASE_URL = "https://api.featherless.ai/v1"

# ---------------------------------------------------------------------------
# System prompt — suporte tier-1 de telecom (fibra óptica + TV por assinatura)
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """\
Você é Bia, assistente virtual de suporte técnico da operadora. Atende clientes de \
internet fibra óptica e TV por assinatura.

Seu objetivo é resolver problemas de nível 1 sem precisar de um atendente humano. \
Seja direto, cordial e use linguagem simples.

== CHECKLIST NÍVEL 1 (siga essa ordem antes de desistir) ==
1. Roteador está ligado na tomada? A luz de energia está acesa?
2. O cabo que sai da parede está bem conectado na porta WAN do roteador?
3. Já tentou reiniciar o roteador? (desligue da tomada por 10 segundos e ligue novamente)
4. Após reiniciar, aguarde 2 minutos e teste novamente.
5. Para TV: o cabo HDMI ou coaxial está firme? A TV está na entrada correta (ex.: HDMI 1)?
6. Outros dispositivos na mesma rede têm o mesmo problema?

== QUANDO RESOLVER ==
- O cliente confirma que o problema sumiu após seguir os passos.
- Emita: {"action": "resolved", "text": "<mensagem de encerramento>"}

== QUANDO ESCALAR ==
- O cliente já fez todos os passos e o problema persiste.
- O cliente pede explicitamente para falar com um atendente ou humano.
- O assunto é fatura, mudança de plano, cancelamento ou reclamação.
- Emita: {"action": "escalate", "text": "<mensagem ao cliente>", \
"reason": "<motivo em 1 frase>"}

== FORMATO DE RESPOSTA (OBRIGATÓRIO) ==
Responda APENAS com um objeto JSON válido, sem markdown, sem texto fora do JSON.

Para continuar o atendimento:
{"action": "reply", "text": "<sua mensagem para o cliente>"}

Para encerrar como resolvido:
{"action": "resolved", "text": "<mensagem de encerramento>"}

Para escalar para humano:
{"action": "escalate", "text": "<mensagem ao cliente>", "reason": "<motivo>"}
"""

_ESCALATION_REPLY = (
    "Vou transferir você para um de nossos atendentes agora. "
    "Por favor, aguarde um momento."
)
_ERROR_REASON = "llm_error"


# ---------------------------------------------------------------------------
# BotDecision — saída tipada de um bot turn
# ---------------------------------------------------------------------------
@dataclass
class BotDecision:
    action: Literal["reply", "resolved", "escalate"]
    reply_text: str
    escalation_reason: str | None = None


# ---------------------------------------------------------------------------
# BotAgentService
# ---------------------------------------------------------------------------
class BotAgentService:
    """
    Converte um histórico de MessageModel em uma BotDecision chamando a Featherless AI.

    Instanciar uma vez e reutilizar (o AsyncOpenAI mantém o pool de conexões).
    """

    def __init__(self) -> None:
        self._client = AsyncOpenAI(
            api_key=settings.featherless_api_key,
            base_url=_FEATHERLESS_BASE_URL,
        )
        self._model = settings.featherless_model

    async def run_turn(self, messages: list[MessageModel]) -> BotDecision:
        """
        Executa um turno do bot.

        Args:
            messages: histórico completo da conversa, ordenado por created_at asc.
                      Mensagens inbound → role "user".
                      Mensagens outbound → role "assistant".

        Returns:
            BotDecision com action, reply_text e escalation_reason opcional.
            Nunca levanta exceção — falhas internas viram action="escalate".
        """
        if not messages:
            return BotDecision(
                action="escalate",
                reply_text=_ESCALATION_REPLY,
                escalation_reason="no_messages",
            )

        # Forçar escalação se o bot já respondeu demais (evita loop infinito)
        inbound_count = sum(1 for m in messages if m.direction == "inbound")
        if inbound_count >= settings.bot_max_turns:
            return BotDecision(
                action="escalate",
                reply_text=_ESCALATION_REPLY,
                escalation_reason="max_turns_reached",
            )

        chat_messages = _build_chat_messages(messages)

        try:
            completion = await self._client.chat.completions.create(
                model=self._model,
                temperature=0.2,
                # Nota: não usamos response_format={"type":"json_object"} porque
                # nem todos os modelos open-source na Featherless suportam JSON mode.
                # O parser abaixo extrai o JSON mesmo que o modelo adicione texto extra.
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    *chat_messages,
                ],
            )
            raw = completion.choices[0].message.content or ""
            return _parse_decision(raw)
        except Exception:
            log.exception("BotAgentService: erro ao chamar Featherless AI")
            return BotDecision(
                action="escalate",
                reply_text=_ESCALATION_REPLY,
                escalation_reason=_ERROR_REASON,
            )


# ---------------------------------------------------------------------------
# Helpers privados
# ---------------------------------------------------------------------------
def _build_chat_messages(messages: list[MessageModel]) -> list[dict[str, str]]:
    """Converte MessageModel em formato de chat messages (role/content)."""
    result = []
    for msg in messages:
        role = "user" if msg.direction == "inbound" else "assistant"
        result.append({"role": role, "content": msg.body})
    return result


def _extract_json(raw: str) -> str:
    """
    Extrai o primeiro objeto JSON da resposta do modelo.

    Modelos open-source frequentemente envolvem o JSON em blocos markdown
    (```json ... ```) ou adicionam texto antes/depois. Esta função tenta
    três estratégias em ordem:
      1. Parse direto (modelo seguiu as instruções).
      2. Extrai de bloco ```json ... ```.
      3. Extrai a primeira substring que começa em '{' e termina em '}'.
    """
    raw = raw.strip()

    # Estratégia 1: JSON limpo
    if raw.startswith("{"):
        return raw

    # Estratégia 2: bloco markdown ```json ... ```
    md_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if md_match:
        return md_match.group(1)

    # Estratégia 3: primeiro { ... } encontrado
    brace_match = re.search(r"\{.*\}", raw, re.DOTALL)
    if brace_match:
        return brace_match.group(0)

    return raw  # deixa o json.loads falhar e escalar


def _parse_decision(raw: str) -> BotDecision:
    """
    Faz parse do JSON retornado pelo LLM.

    Qualquer desvio do esquema esperado cai no branch de escalação para não
    deixar o cliente sem resposta.
    """
    try:
        data = json.loads(_extract_json(raw))
    except json.JSONDecodeError:
        log.warning("BotAgentService: resposta não é JSON válido: %r", raw[:200])
        return BotDecision(
            action="escalate",
            reply_text=_ESCALATION_REPLY,
            escalation_reason="invalid_json",
        )

    action = data.get("action")
    text = str(data.get("text", "")).strip()

    if action == "reply":
        if not text:
            text = "Desculpe, tive um problema. Pode repetir sua dúvida?"
        return BotDecision(action="reply", reply_text=text)

    if action == "resolved":
        if not text:
            text = "Fico feliz em ter ajudado! Qualquer dúvida, é só chamar."
        return BotDecision(action="resolved", reply_text=text)

    if action == "escalate":
        reason = str(data.get("reason", "bot_escalation")).strip()
        if not text:
            text = _ESCALATION_REPLY
        return BotDecision(action="escalate", reply_text=text, escalation_reason=reason)

    # action desconhecida
    log.warning("BotAgentService: action desconhecida %r", action)
    return BotDecision(
        action="escalate",
        reply_text=_ESCALATION_REPLY,
        escalation_reason="unknown_action",
    )