import { useEffect, useState } from "react"
import { fetchTicket } from "../api"
import { actionLabel, formatClock, STATUS_LABEL } from "../labels"
import type { Status, TicketCard, TicketDetail, Transitions } from "../types"

export function Drawer({
  card,
  transitions,
  onClose,
  onMove,
}: {
  card: TicketCard
  transitions: Transitions
  onClose: () => void
  onMove: (id: string, target: Status) => void
}) {
  const [detail, setDetail] = useState<TicketDetail | null>(null)
  const [error, setError] = useState<string | null>(null)
  const targets = transitions[card.status] ?? []

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onClose()
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [onClose])

  useEffect(() => {
    let cancelled = false
    setError(null)
    fetchTicket(card.id)
      .then((next) => {
        if (!cancelled) setDetail(next)
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "Falha ao carregar")
      })
    return () => {
      cancelled = true
    }
  }, [card.id, card.message_count, card.updated_at, card.status])

  const messages = [...(detail?.messages ?? [])].sort((a, b) => a.created_at.localeCompare(b.created_at))

  return (
    <aside className="drawer">
      <header>
        <div>
          <p className="eyebrow">{card.channel ?? "canal"}</p>
          <h2>{card.external_id ?? card.sender ?? "Contato"}</h2>
          <p>{STATUS_LABEL[card.status]}</p>
        </div>
        <button type="button" className="ghost" onClick={onClose}>
          Fechar
        </button>
      </header>

      <div className="drawer-actions">
        {targets.length === 0 ? (
          <p>Fechado não tem saída. A máquina de estados para aqui.</p>
        ) : (
          targets.map((target) => (
            <button key={target} type="button" onClick={() => onMove(card.id, target)}>
              {actionLabel(card.status, target)}
            </button>
          ))
        )}
      </div>

      <div className="thread">
        {error ? <p className="thread-note">{error}</p> : null}
        {!error && detail === null ? <p className="thread-note">Carregando histórico…</p> : null}
        {messages.map((message) => (
          <article key={message.id} data-direction={message.direction}>
            <p>{message.body}</p>
            <footer>
              <span>{message.sender}</span>
              <time dateTime={message.created_at}>{formatClock(message.created_at)}</time>
            </footer>
            <code>{message.external_message_id}</code>
          </article>
        ))}
      </div>
    </aside>
  )
}
