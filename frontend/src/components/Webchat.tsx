import { useEffect, useRef, useState } from "react"
import { apiUrl, fetchBoard, fetchTicket, sendWebchat } from "../api"
import { formatClock } from "../labels"
import type { HubEvent, Status, TicketMessage } from "../types"

const SESSION_KEY = "omnihub.webchat.session"

type PendingMessage = {
  id: string
  body: string
  created_at: string
}

function readSession(): string {
  const existing = localStorage.getItem(SESSION_KEY)
  if (existing) return existing
  const created = `sess-${crypto.randomUUID()}`
  localStorage.setItem(SESSION_KEY, created)
  return created
}

function concernsSession(event: HubEvent, sessionId: string): boolean {
  if ("ticket" in event) {
    return event.ticket.channel === "webchat" && event.ticket.external_id === sessionId
  }
  if (
    event.type === "job.queued" ||
    event.type === "webhook.duplicate" ||
    event.type === "message.duplicate"
  ) {
    return event.sender === sessionId
  }
  return false
}

function speaker(message: TicketMessage): string {
  if (message.direction === "inbound") return "Você"
  if (message.sender === "bot") return "Bia"
  if (message.sender === "atendente") return "Atendente"
  return message.sender || "Atendimento"
}

function statusLine(status: Status | null): string {
  if (status === "bot") return "A Bia está neste atendimento."
  if (status === "new" || status === "open" || status === "waiting_customer") {
    return "Um atendente está com este atendimento."
  }
  if (status === "resolved" || status === "closed") {
    return "Atendimento encerrado. Uma nova mensagem abre outro."
  }
  return "Escreva sua mensagem. A Bia responde por aqui."
}

export function Webchat() {
  const sessionId = useRef(readSession()).current
  const [messages, setMessages] = useState<TicketMessage[]>([])
  const [pending, setPending] = useState<PendingMessage[]>([])
  const [status, setStatus] = useState<Status | null>(null)
  const [draft, setDraft] = useState("")
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const endRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    document.title = "Omnihub — chat"
  }, [])

  useEffect(() => {
    let cancelled = false

    async function sync() {
      const board = await fetchBoard()
      const card = board.tickets
        .filter((item) => item.channel === "webchat" && item.external_id === sessionId)
        .sort((a, b) => (b.updated_at ?? "").localeCompare(a.updated_at ?? ""))[0]
      if (!card) {
        if (!cancelled) setStatus(null)
        return
      }
      const detail = await fetchTicket(card.id)
      if (cancelled) return
      const next = [...detail.messages].sort((a, b) => a.created_at.localeCompare(b.created_at))
      setMessages(next)
      setStatus(detail.status)
      setPending((current) => current.filter((item) => !next.some((message) => message.external_message_id === item.id)))
    }

    void sync().catch(() => undefined)
    const timer = window.setInterval(() => {
      void sync().catch(() => undefined)
    }, 3000)
    const source = new EventSource(apiUrl("/events"))
    source.onmessage = (message) => {
      try {
        const event = JSON.parse(message.data) as HubEvent
        if (concernsSession(event, sessionId)) void sync().catch(() => undefined)
      } catch {
        // A malformed frame does not stop the next one.
      }
    }

    return () => {
      cancelled = true
      window.clearInterval(timer)
      source.close()
    }
  }, [sessionId])

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" })
  }, [messages.length, pending.length])

  async function send() {
    const text = draft.trim()
    if (!text || busy) return
    const messageId = `webchat.${crypto.randomUUID()}`
    setBusy(true)
    setError(null)
    setPending((current) => [
      ...current,
      { id: messageId, body: text, created_at: new Date().toISOString() },
    ])
    setDraft("")
    try {
      await sendWebchat({ messageId, sessionId, text })
    } catch (reason) {
      setPending((current) => current.filter((item) => item.id !== messageId))
      setDraft(text)
      setError(reason instanceof Error ? reason.message : "Não consegui enviar")
    } finally {
      setBusy(false)
    }
  }

  const waiting = pending.filter((item) => !messages.some((message) => message.external_message_id === item.id))
  const empty = messages.length === 0 && waiting.length === 0
  const presence =
    status === "resolved" || status === "closed"
      ? "encerrado"
      : status === "new" || status === "open" || status === "waiting_customer"
        ? "atendente"
        : "online"

  return (
    <div className="webchat">
      <div className="webchat-shell">
        <header className="webchat-top">
          <div className="webchat-identity">
            <span className="webchat-avatar" aria-hidden="true">
              B
            </span>
            <div>
              <p className="eyebrow">Suporte</p>
              <h1>Bia</h1>
              <p className={`webchat-presence is-${presence}`}>
                <i />
                {presence === "encerrado" ? "Atendimento encerrado" : presence === "atendente" ? "Atendente na conversa" : "Online agora"}
              </p>
            </div>
          </div>
          <a className="chip" href="/mesa">
            Atendente
          </a>
        </header>

        <section className="webchat-thread" aria-label="Conversa">
          <p className={`webchat-status${status ? ` is-${status}` : ""}`}>{statusLine(status)}</p>
          {empty ? (
            <div className="webchat-empty">
              <span className="webchat-empty-mark" aria-hidden="true">
                B
              </span>
              <strong>Olá, eu sou a Bia.</strong>
              <p>Conte o que você precisa. Se preferir, um atendente assume daqui.</p>
              <div className="webchat-prompts">
                {["Preciso de ajuda", "Quero falar com alguém", "Como funciona o atendimento?"].map((prompt) => (
                  <button key={prompt} type="button" className="ghost" onClick={() => setDraft(prompt)}>
                    {prompt}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="bubbles">
              {messages.map((message) => (
                <article key={message.id} data-direction={message.direction} data-speaker={message.sender || "cliente"}>
                  <p>{message.body}</p>
                  <footer>
                    <span>{speaker(message)}</span>
                    <time dateTime={message.created_at}>{formatClock(message.created_at)}</time>
                  </footer>
                </article>
              ))}
              {waiting.map((message) => (
                <article key={message.id} data-direction="inbound" data-pending="true">
                  <p>{message.body}</p>
                  <footer>
                    <span>Você</span>
                    <time dateTime={message.created_at}>enviando</time>
                  </footer>
                </article>
              ))}
              <div ref={endRef} />
            </div>
          )}
        </section>

        <form
          className="webchat-form"
          onSubmit={(event) => {
            event.preventDefault()
            void send()
          }}
        >
          <textarea
            rows={1}
            value={draft}
            placeholder="Escreva sua mensagem"
            aria-label="Mensagem"
            disabled={busy}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault()
                void send()
              }
            }}
          />
          <button type="submit" disabled={busy || !draft.trim()} aria-label="Enviar">
            <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
              <path fill="currentColor" d="M4 11h11.2l-4.1-4.1 1.4-1.4L19.6 12l-7.1 6.5-1.4-1.4 4.1-4.1H4v-2Z" />
            </svg>
          </button>
          {error ? <p className="thread-note">{error}</p> : null}
        </form>
      </div>
    </div>
  )
}
