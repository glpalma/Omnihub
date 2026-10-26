# Omnihub

Atendimento **omnichannel**: recebe mensagens de WhatsApp e webchat via webhook, normaliza em um domínio único, processa em fila e entrega para o atendente numa mesa (React) atualizada ao vivo por SSE, além da API REST.

Projeto pessoal construído para demonstrar domínio de back-end Python assíncrono, integração via fila, e uma interface de operação em cima da mesma API.

---

## Por que isso existe

Plataformas de atendimento como as da VulcaNet recebem eventos de WhatsApp, voz, redes sociais e chat do site simultaneamente. Cada canal tem um formato de payload diferente. O Omnihub simula o núcleo desse tipo de plataforma: um gateway de ingestão que normaliza eventos heterogêneos em um modelo único (`Conversation` → `Message` → `Ticket`) e os processa de forma assíncrona via fila.

---

## Decisões de design

| Decisão | Alternativa considerada | Por quê essa |
|---|---|---|
| **FastAPI** | Flask, Django | Async nativo; gera OpenAPI/Swagger automaticamente a partir de type hints |
| **ARQ + Redis** como fila | Celery + RabbitMQ; fila em tabela Postgres | ARQ é async-nativo e leve; combina com o event loop do FastAPI; Redis é atomic para pop de fila |
| **PostgreSQL + SQLAlchemy 2.0 async** | MongoDB; SQLite | SQL com relações claras (conversa → mensagens → ticket); SQLAlchemy 2.0 tem suporte nativo a async sem bloquear o event loop |
| **`create_all` no startup** | Alembic migrations | MVP deliberado; Alembic é o upgrade path (Nível 2) — marcado no código com `ponytail:` comment |
| **Resposta `202 Accepted` no webhook** | Processar de forma síncrona | A Meta reenvia o evento se não receber resposta rápida; processar de forma síncrona tornaria o endpoint sujeito a timeouts e duplicatas |
| **Dedupe por `external_message_id`** (wamid no WhatsApp, `message_id` no webchat) | Apenas confiar na fila não reenviar | Webhooks reais reenviam; a defesa precisa estar no endpoint (antes de enfileirar) E no worker (na escrita) |
| **SQLite in-memory nos testes** | testcontainers + Postgres real | Sem infraestrutura necessária para `pytest`; `Uuid` genérico do SQLAlchemy 2.0 é compatível com ambos |


---

## Arquitetura

```
                         ┌──────────────────────────────────────────┐
  WhatsApp / webchat     │                                          │
  (ou a mesa simulando)─►│  POST /webhooks/whatsapp                 │
                         │  POST /webhooks/webchat                  │
                         │  ① valida payload (Pydantic)             │
                         │  ② dedupe por external_message_id        │
                         │  ③ enfileira job no Redis                │
                         │  ④ publica evento e responde 202         │
                         │                  │                       │
                         │         Redis (fila ARQ + pub/sub)       │
                         │                  │                       │
                         │           [worker ARQ]                   │
                         │  ⑤ upsert Conversation                   │
                         │  ⑥ insere Message                        │
                         │  ⑦ cria ou reutiliza Ticket              │
                         │                  │                       │
  Mesa :5173             │  GET /board          PostgreSQL          │
  Quadro / curl /docs ──►│  GET /events  (SSE)                      │
                         │  GET /tickets  ·  GET /tickets/{id}      │
                         │  POST /tickets/{id}/transition           │
                         │  POST /tickets/{id}/messages             │
                         └──────────────────────────────────────────┘
```

O worker publica no canal `omnihub:events`. `GET /events` assina esse canal com uma conexão Redis própria (o pool do ARQ fica livre para enfileirar) e encaminha os eventos ao navegador.

```
app/
  api/          rotas FastAPI (health, board, stream, tickets, webhooks)
  domain/       entidades puras + máquina de estados (sem DB)
  db/           modelos SQLAlchemy 2.0 async + sessão
  workers/      tasks ARQ (WhatsApp e inbound genérico) + WorkerSettings
  events.py     cartão do quadro e publicação no canal Redis
  core/         config (pydantic-settings)
frontend/       mesa e quadro (React + Vite); lê /board e /events
tests/
  domain/       testes unitários da máquina de estados
  api/          testes HTTP (health, tickets, board, webchat, resposta)
  integration/  webhook → task → ticket, nos dois canais
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

# Subir todos os serviços (api + worker + frontend + postgres + redis)
docker compose up --build
```

Aguarde até ver `Application startup complete` nos logs da `api`. Então:

```bash
# Verificar que a API está saudável
curl http://localhost:8000/health
# → {"status":"ok"}

# Mesa de atendimento (conversas, resposta do atendente, quadro ao vivo)
open http://localhost:5173

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
# → {"queued":true} — a mensagem já existe, sem segundo job
```

O webchat segue a mesma regra, usando `message_id` no lugar do wamid.

### 7. Simular o chat do site

```bash
curl -s -X POST http://localhost:8000/webhooks/webchat \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "sess-carla",
    "message_id": "webchat.ABC001",
    "text": "Oi pelo site"
  }'
# → {"queued":true}
```

O job na fila é `process_inbound_message`. O worker grava o canal `webchat` e usa `session_id` como identificador da conversa.

### 8. Responder como atendente

```bash
curl -s -X POST http://localhost:8000/tickets/<TICKET_ID>/messages \
  -H "Content-Type: application/json" \
  -d '{"body": "Olá, já estou vendo o seu pedido"}'
```

A resposta fica na conversa com `direction: "outbound"` e `sender: "atendente"`. Se o ticket está `new`, `waiting_customer` ou `resolved`, essa chamada também o leva para `open`. Ticket `closed` responde `422`.

### 9. Quadro e stream ao vivo

```bash
# Snapshot que a mesa carrega: cartões + transições permitidas
curl -s http://localhost:8000/board | python3 -m json.tool

# Server-Sent Events (job.queued, ticket.created, message.appended,
# ticket.transitioned, message.sent, webhook.duplicate, message.duplicate)
curl -N http://localhost:8000/events
```

---

## Rodar os testes

Os testes usam SQLite in-memory — **não precisam de Docker rodando**.

```bash
# Instalar uv se não tiver
pip install uv

# Rodar todos os 40 testes
uv run --extra dev pytest -v
```

---

## Fluxo de estados do Ticket

```
new ──► open ◄──► waiting_customer
         │              │
         ▼              ▼
      resolved ──► closed
         │
         └──► open
```

`closed` é terminal. `resolved` volta para `open` só pela ação do atendente.

Uma mensagem nova do cliente entra no ticket que ainda está `new`, `open` ou `waiting_customer`, sem mudar o status. Se o ticket da conversa já está `resolved` ou `closed`, o worker abre outro ticket. Quem muda o status é o atendente, pela transição ou ao responder (`POST /tickets/{id}/messages` abre o ticket quando a transição para `open` é válida).

Transições inválidas retornam `422 Unprocessable Entity` com mensagem descritiva.
