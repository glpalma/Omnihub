import { useEffect, useRef, useState } from "react"
import { fetchTicket, sendAgentReply, sendWebchat, sendWhatsApp } from "../api"
import { actionLabel, formatClock, STATUS_LABEL } from "../labels"
import type { FeedItem, Status, TicketCard, TicketMessage, Transitions } from "../types"

type ChannelName = "whatsapp" | "webchat"

type Customer = {
  name: string
  channel: ChannelName
  externalId: string
  endpoint: string
}

const CUSTOMERS: Customer[] = [
  {
    name: "Ana Lima",
    channel: "whatsapp",
    externalId: "+5511999990001",
    endpoint: "POST /webhooks/whatsapp",
  },
  {
    name: "Bruno Costa",
    channel: "whatsapp",
    externalId: "+5511988882222",
    endpoint: "POST /webhooks/whatsapp",
  },
  {
    name: "Carla Nunes",
    channel: "webchat",
    externalId: "sess-carla",
    endpoint: "POST /webhooks/webchat",
  },
  {
    name: "Diego Alves",
    channel: "webchat",
    externalId: "sess-diego",
    endpoint: "POST /webhooks/webchat",
  },
]

function freshId(channel: ChannelName): string {
  const token = crypto.randomUUID()
  return channel === "whatsapp" ? `wamid.ui.${token}` : `webchat.${token}`
}

export function Desk({
  cards,
  transitions,
  selectedId,
  latest,
  onSelect,
  onMove,
  onSimulated,
}: {
  cards: TicketCard[]
  transitions: Transitions
  selectedId: string | null
  latest: FeedItem | null
  onSelect: (id: string) => void
  onMove: (id: string, target: Status) => void
  onSimulated: (channel: string, externalId: string) => void
}) {
  const [filter, setFilter] = useState<"all" | ChannelName>("all")
  const visible = cards
    .filter((card) => filter === "all" || card.channel === filter)
    .slice()
    .sort((a, b) => (b.updated_at ?? "").localeCompare(a.updated_at ?? ""))
  const selected = cards.find((card) => card.id === selectedId) ?? null

  return (
    <div className="desk">
      <section className="panel inbox">
        <header>
          <h2>Conversas</h2>
          <div className="filters">
            {(
              [
                ["all", "Todas"],
                ["whatsapp", "WhatsApp"],
                ["webchat", "Webchat"],
              ] as const
            ).map(([id, label]) => (
              <button
                key={id}
                type="button"
                className={filter === id ? "chip is-on" : "chip"}
                onClick={() => setFilter(id)}
              >
                {label}
              </button>
            ))}
          </div>
        </header>
        <ul>
          {visible.length === 0 ? (
            <li className="inbox-empty">Nenhuma conversa neste filtro. Dispare um webhook ao lado.</li>
          ) : (
            visible.map((card) => (
              <li key={card.id}>
                <button
                  type="button"
                  className={card.id === selectedId ? "row is-on" : "row"}
                  onClick={() => onSelect(card.id)}
                >
                  <span className="channel">{card.channel ?? "canal"}</span>
                  <strong>{card.external_id ?? "contato"}</strong>
                  <em>{card.last_message ?? "Sem mensagem"}</em>
                  <span>{STATUS_LABEL[card.status]}</span>
                </button>
              </li>
            ))
          )}
        </ul>
      </section>

      <Thread card={selected} transitions={transitions} onMove={onMove} onCustomerSent={onSimulated} />

      <section className="panel simulators">
        <header>
          <h2>Webhooks de teste</h2>
          <p>Cada cliente fala por um contrato diferente. A resposta entra na conversa ao lado.</p>
        </header>
        {latest ? (
          <p className="desk-latest">
            <strong>{latest.title}</strong>
            <span>{latest.detail}</span>
          </p>
        ) : null}
        <div className="customer-list">
          {CUSTOMERS.map((customer) => (
            <CustomerForm key={customer.externalId} customer={customer} onSimulated={onSimulated} />
          ))}
        </div>
      </section>
    </div>
  )
}

function Thread({
  card,
  transitions,
  onMove,
  onCustomerSent,
}: {
  card: TicketCard | null
  transitions: Transitions
  onMove: (id: string, target: Status) => void
  onCustomerSent: (channel: string, externalId: string) => void
}) {
  const [messages, setMessages] = useState<TicketMessage[]>([])
  const [draft, setDraft] = useState("")
  const [role, setRole] = useState<"agent" | "customer">("agent")
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const endRef = useRef<HTMLDivElement>(null)
  const targets = card ? (transitions[card.status] ?? []) : []

  useEffect(() => {
    if (!card) {
      setMessages([])
      return
    }
    let cancelled = false
    fetchTicket(card.id)
      .then((detail) => {
        if (!cancelled) {
          setMessages(
            [...detail.messages].sort((a, b) => a.created_at.localeCompare(b.created_at)),
          )
        }
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "Falha ao carregar")
      })
    return () => {
      cancelled = true
    }
  }, [card?.id, card?.message_count, card?.updated_at, card?.status, card?.last_external_message_id])

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" })
  }, [messages.length])

  async function reply() {
    if (!card) return
    const text = draft.trim()
    if (!text) return
    setBusy(true)
    setError(null)
    try {
      if (role === "customer") {
        await sendAsCustomer(card, text)
        if (card.channel && card.external_id) onCustomerSent(card.channel, card.external_id)
      } else {
        await sendAgentReply(card.id, text)
      }
      setDraft("")
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao responder")
    } finally {
      setBusy(false)
    }
  }

  if (!card) {
    return (
      <section className="panel thread">
        <p className="thread-note">Escolha uma conversa ou dispare um webhook para ela nascer aqui.</p>
      </section>
    )
  }

  const closed = card.status === "closed"
  const agentBlocked = closed && role === "agent"
  const placeholder = agentBlocked
    ? "Ticket fechado. O cliente ainda pode escrever."
    : role === "customer"
      ? "Responder como cliente"
      : "Responder como atendente"

  return (
    <section className="panel thread">
      <header className="thread-head">
        <div>
          <p className="eyebrow">{card.channel}</p>
          <h2>{card.external_id}</h2>
          <p>{STATUS_LABEL[card.status]}</p>
        </div>
        <div className="drawer-actions">
          {targets.map((target) => (
            <button key={target} type="button" className="ghost" onClick={() => onMove(card.id, target)}>
              {actionLabel(card.status, target)}
            </button>
          ))}
        </div>
      </header>
      <div className="bubbles">
        {messages.map((message) => (
          <article key={message.id} data-direction={message.direction}>
            <p>{message.body}</p>
            <footer>
              <span>{message.direction === "outbound" ? "Você" : message.sender}</span>
              <time dateTime={message.created_at}>{formatClock(message.created_at)}</time>
            </footer>
          </article>
        ))}
        <div ref={endRef} />
      </div>
      <form
        className={role === "customer" ? "agent-reply is-customer" : "agent-reply"}
        onSubmit={(event) => {
          event.preventDefault()
          void reply()
        }}
      >
        <div className="reply-roles" role="group" aria-label="Quem está falando">
          <button
            type="button"
            className={role === "agent" ? "chip is-on" : "chip"}
            onClick={() => setRole("agent")}
          >
            Atendente
          </button>
          <button
            type="button"
            className={role === "customer" ? "chip is-on" : "chip"}
            onClick={() => setRole("customer")}
          >
            Cliente
          </button>
        </div>
        <textarea
          value={draft}
          disabled={agentBlocked || busy}
          placeholder={placeholder}
          aria-label={placeholder}
          rows={2}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault()
              void reply()
            }
          }}
        />
        <button type="submit" disabled={agentBlocked || busy || !draft.trim()}>
          Enviar
        </button>
      </form>
      {error ? <p className="thread-note">{error}</p> : null}
    </section>
  )
}

async function sendAsCustomer(card: TicketCard, text: string): Promise<void> {
  const channel = card.channel
  const externalId = card.external_id
  if ((channel !== "whatsapp" && channel !== "webchat") || !externalId) {
    throw new Error("Esta conversa não tem canal para o cliente responder.")
  }
  const messageId = freshId(channel)
  if (channel === "whatsapp") {
    await sendWhatsApp({ wamid: messageId, sender: externalId, body: text })
  } else {
    await sendWebchat({ messageId, sessionId: externalId, text })
  }
}

function CustomerForm({
  customer,
  onSimulated,
}: {
  customer: Customer
  onSimulated: (channel: string, externalId: string) => void
}) {
  const [text, setText] = useState("Oi, preciso de ajuda")
  const [lastId, setLastId] = useState<string | null>(null)
  const [note, setNote] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function send(reuse: boolean) {
    const messageId = reuse && lastId ? lastId : freshId(customer.channel)
    const body = text.trim()
    if (!body) {
      setNote("Escreva uma mensagem.")
      return
    }
    setBusy(true)
    try {
      if (customer.channel === "whatsapp") {
        await sendWhatsApp({ wamid: messageId, sender: customer.externalId, body })
      } else {
        await sendWebchat({ messageId, sessionId: customer.externalId, text: body })
      }
      setLastId(messageId)
      setNote(reuse ? `202 · mesmo id ${messageId}` : `202 · ${messageId}`)
      onSimulated(customer.channel, customer.externalId)
    } catch (reason) {
      setNote(reason instanceof Error ? reason.message : "Falha no webhook")
    } finally {
      setBusy(false)
    }
  }

  const preview =
    customer.channel === "whatsapp"
      ? `{ "from": "${customer.externalId}", "text": { "body": "…" } }`
      : `{ "session_id": "${customer.externalId}", "text": "…" }`

  return (
    <form
      className="customer"
      onSubmit={(event) => {
        event.preventDefault()
        void send(false)
      }}
    >
      <header>
        <strong>{customer.name}</strong>
        <span className="channel">{customer.channel}</span>
      </header>
      <p>{customer.externalId}</p>
      <code>{customer.endpoint}</code>
      <code className="payload">{preview}</code>
      <textarea
        rows={2}
        value={text}
        onChange={(event) => setText(event.target.value)}
        aria-label={`Mensagem de ${customer.name}`}
      />
      <div className="composer-actions">
        <button type="submit" disabled={busy}>
          Disparar
        </button>
        <button type="button" className="ghost" disabled={busy || !lastId} onClick={() => void send(true)}>
          Repetir id
        </button>
      </div>
      {note ? <p className="customer-note">{note}</p> : null}
    </form>
  )
}
