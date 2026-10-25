# Omnihub

Backend de atendimento **omnichannel**: recebe mensagens de múltiplos canais (WhatsApp, webchat) via webhook, normaliza em um domínio único e expõe uma API REST para gerenciar tickets de suporte.

Projeto pessoal construído para demonstrar domínio de back-end Python assíncrono, integração via fila, e design de API documentada.

---

## Por que isso existe

Plataformas de atendimento como as da VulcaNet recebem eventos de WhatsApp, voz, redes sociais e chat do site simultaneamente. Cada canal tem um formato de payload diferente. O Omnihub simula o núcleo desse tipo de plataforma: um gateway de ingestão que normaliza eventos heterogêneos em um modelo único (`Conversation` → `Message` → `Ticket`) e os processa de forma assíncrona via fila.

---

## Arquitetura

```
                         ┌─────────────────────────────────────┐
  WhatsApp Cloud API     │                                     │
  (ou curl simulando) ──►│  POST /webhooks/whatsapp            │
                         │  ① valida payload (Pydantic)        │
                         │  ② dedupe por wamid (idempotência)  │
                         │  ③ enfileira job no Redis           │
                         │  ④ responde 202 imediatamente       │
                         │                  │                  │
                         │              Redis (fila)           │
                         │                  │                  │
                         │           [worker ARQ]              │
                         │  ⑤ upsert Conversation              │
                         │  ⑥ insere Message                   │
                         │  ⑦ cria/reutiliza Ticket            │
                         │                  │                  │
  curl / Swagger ───────►│  GET /tickets   PostgreSQL          │
                         │  GET /tickets/{id}                  │
                         │  POST /tickets/{id}/transition      │
                         └─────────────────────────────────────┘
```

```
app/
  api/          rotas FastAPI (health, tickets, webhooks)
  domain/       entidades puras + máquina de estados (sem DB)
  db/           modelos SQLAlchemy 2.0 async + sessão
  workers/      task ARQ + WorkerSettings
  core/         config (pydantic-settings)
tests/
  domain/       testes unitários da máquina de estados
  api/          testes HTTP (health, tickets)
  integration/  webhook → task → ticket end-to-end
```

---

## Pré-requisitos

- Docker Desktop instalado e **em execução**
- `git`

Nenhuma instalação de Python, Redis ou Postgres necessária — o Docker cuida de tudo.

---

## Como rodar

```bash
git clone https://github.com/glpalma/Omnihub.git
cd Omnihub

# Copiar configuração padrão (já pronto para uso local)
cp .env.example .env

# Subir todos os serviços (api + worker + postgres + redis)
docker compose up --build
```

Aguarde até ver `Application startup complete` nos logs da `api`. Então:

```bash
# Verificar que a API está saudável
curl http://localhost:8000/health
# → {"status":"ok"}

# Documentação interativa (Swagger)
open http://localhost:8000/docs
```

---

## Exemplos de uso

### 1. Simular uma mensagem do WhatsApp (curl)

```bash
curl -s -X POST http://localhost:8000/webhooks/whatsapp \
  -H "Content-Type: application/json" \
  -d '{
    "object": "whatsapp_business_account",
    "entry": [{
      "id": "123",
      "changes": [{
        "field": "messages",
        "value": {
          "messaging_product": "whatsapp",
          "messages": [{
            "id": "wamid.ABC001",
            "from": "+5511999990001",
            "timestamp": "1700000000",
            "type": "text",
            "text": { "body": "Preciso de ajuda com meu pedido" }
          }]
        }
      }]
    }]
  }'
# → {"queued":true}
```

O worker processa o job em segundo plano. Após 1–2 segundos:

### 2. Listar tickets

```bash
curl -s http://localhost:8000/tickets | python3 -m json.tool
```

### 3. Filtrar por status ou canal

```bash
curl -s "http://localhost:8000/tickets?status=new&channel=whatsapp" | python3 -m json.tool
```

### 4. Ver detalhe com histórico de mensagens

```bash
# Substitua <TICKET_ID> pelo id retornado no passo anterior
curl -s http://localhost:8000/tickets/<TICKET_ID> | python3 -m json.tool
```

### 5. Mover o ticket pelo fluxo (máquina de estados)

```bash
# new → open
curl -s -X POST http://localhost:8000/tickets/<TICKET_ID>/transition \
  -H "Content-Type: application/json" \
  -d '{"target_status": "open"}'

# open → waiting_customer
curl -s -X POST http://localhost:8000/tickets/<TICKET_ID>/transition \
  -H "Content-Type: application/json" \
  -d '{"target_status": "waiting_customer"}'

# Transição inválida (ex: new → closed) retorna 422
curl -s -X POST http://localhost:8000/tickets/<TICKET_ID>/transition \
  -H "Content-Type: application/json" \
  -d '{"target_status": "closed"}'
# → {"detail":"Cannot transition from 'new' to 'closed'..."}
```

### 6. Teste de idempotência (reenvio com mesmo wamid)

```bash
# Enviar a mesma mensagem duas vezes com o mesmo id (wamid.ABC001)
# O segundo envio deve retornar 202 mas NÃO criar um ticket/mensagem duplicado
curl -s -X POST http://localhost:8000/webhooks/whatsapp \
  -H "Content-Type: application/json" \
  -d '{ "object": "whatsapp_business_account", "entry": [{ "id": "123", "changes": [{ "field": "messages", "value": { "messaging_product": "whatsapp", "messages": [{ "id": "wamid.ABC001", "from": "+5511999990001", "timestamp": "1700000000", "type": "text", "text": { "body": "Preciso de ajuda" } }] } }] }] }'
# → {"queued":true} — mas o ticket já existe, sem duplicata
```

---

## Rodar os testes

Os testes usam SQLite in-memory — **não precisam de Docker rodando**.

```bash
# Instalar uv se não tiver
pip install uv

# Rodar todos os 29 testes
uv run --extra dev pytest -v
```

---

## Decisões de design

| Decisão | Alternativa considerada | Por quê essa |
|---|---|---|
| **FastAPI** | Flask, Django | Async nativo; gera OpenAPI/Swagger automaticamente a partir de type hints |
| **ARQ + Redis** como fila | Celery + RabbitMQ; fila em tabela Postgres | ARQ é async-nativo e leve; combina com o event loop do FastAPI; Redis é atomic para pop de fila |
| **PostgreSQL + SQLAlchemy 2.0 async** | MongoDB; SQLite | SQL com relações claras (conversa → mensagens → ticket); SQLAlchemy 2.0 tem suporte nativo a async sem bloquear o event loop |
| **`create_all` no startup** | Alembic migrations | MVP deliberado; Alembic é o upgrade path (Nível 2) — marcado no código com `ponytail:` comment |
| **Resposta `202 Accepted` no webhook** | Processar de forma síncrona | A Meta reenvia o evento se não receber resposta rápida; processar de forma síncrona tornaria o endpoint sujeito a timeouts e duplicatas |
| **Dedupe por `external_message_id` (wamid)** | Apenas confiar na fila não reenviar | Webhooks reais reenviam; a defesa precisa estar no endpoint (antes de enfileirar) E no worker (na escrita) |
| **SQLite in-memory nos testes** | testcontainers + Postgres real | Sem infraestrutura necessária para `pytest`; `Uuid` genérico do SQLAlchemy 2.0 é compatível com ambos |

---

## Fluxo de estados do Ticket

```
new ──► open ──► waiting_customer ──► resolved ──► closed
         ▲             │                  │
         └─────────────┘                  │
         (cliente respondeu)              └──► open (reaberto)
```

Transições inválidas retornam `422 Unprocessable Entity` com mensagem descritiva.
