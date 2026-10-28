import { useState } from "react"
import { formatClock } from "../labels"
import type { TicketCard } from "../types"

export function BotStrip({
  cards,
  onEscalate,
}: {
  cards: TicketCard[]
  onEscalate: (id: string) => void
}) {
  const [pending, setPending] = useState<TicketCard | null>(null)

  return (
    <>
      <section className="bot-strip" aria-label="Atendimentos em andamento pelo bot">
        <header className="bot-strip-header">
          <span className="bot-strip-label">
            <span className="bot-badge">bot</span>
            Bia está atendendo
          </span>
          <span className="bot-strip-count">
            {cards.length} {cards.length === 1 ? "cliente" : "clientes"}
          </span>
        </header>

        {cards.length === 0 ? (
          <p className="bot-strip-empty">Nenhum cliente com o bot agora.</p>
        ) : (
        <div className="bot-strip-cards">
          {cards.map((card) => (
            <article key={card.id} className="bot-card">
              <div className="bot-card-body">
                <p className="bot-card-contact">
                  {card.external_id ?? card.sender ?? "cliente"}
                </p>
                <p className="bot-card-channel">{card.channel ?? "canal"}</p>
                <p className="bot-card-preview">{card.last_message ?? "—"}</p>
              </div>
              <footer className="bot-card-footer">
                <time dateTime={card.updated_at ?? undefined}>
                  {formatClock(card.updated_at)}
                </time>
                <button
                  type="button"
                  className="ghost bot-card-take"
                  onClick={() => setPending(card)}
                >
                  Assumir
                </button>
              </footer>
            </article>
          ))}
        </div>
        )}
      </section>

      {pending !== null && (
        <div
          className="dialog-overlay"
          role="presentation"
          onClick={(e) => {
            if (e.target === e.currentTarget) setPending(null)
          }}
        >
          <dialog open className="dialog" aria-labelledby="escalate-title">
            <h2 id="escalate-title">Assumir este atendimento?</h2>
            <p>
              Você está retirando{" "}
              <strong>
                {pending.external_id ?? pending.sender ?? "este cliente"}
              </strong>{" "}
              do bot. O ticket entrará na fila de <strong>Novos</strong> e
              precisará de um atendente humano para continuar.
            </p>
            <p className="dialog-warn">
              O bot não responderá mais a este cliente neste ticket.
            </p>
            <div className="dialog-actions">
              <button
                type="button"
                className="ghost"
                onClick={() => setPending(null)}
              >
                Cancelar
              </button>
              <button
                type="button"
                onClick={() => {
                  onEscalate(pending.id)
                  setPending(null)
                }}
              >
                Assumir atendimento
              </button>
            </div>
          </dialog>
        </div>
      )}
    </>
  )
}
