import { useRef } from "react"
import { formatClock, messageCountLabel } from "../labels"
import type { Status, TicketCard } from "../types"

export function TicketCardView({
  card,
  selected,
  onSelect,
  onDragStart,
  onDragEnd,
}: {
  card: TicketCard
  selected: boolean
  onSelect: (id: string) => void
  onDragStart: (card: TicketCard) => void
  onDragEnd: () => void
}) {
  const dragged = useRef(false)

  return (
    <article
      className={selected ? "card is-selected" : "card"}
      draggable
      tabIndex={0}
      onDragStart={(event) => {
        dragged.current = true
        event.dataTransfer.setData("text/plain", card.id)
        event.dataTransfer.effectAllowed = "move"
        onDragStart(card)
      }}
      onDragEnd={() => {
        onDragEnd()
        window.setTimeout(() => {
          dragged.current = false
        }, 0)
      }}
      onClick={() => {
        if (dragged.current) return
        onSelect(card.id)
      }}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault()
          onSelect(card.id)
        }
      }}
    >
      <header>
        <span className="channel">{card.channel ?? "canal"}</span>
        <time dateTime={card.updated_at ?? undefined}>{formatClock(card.updated_at)}</time>
      </header>
      <p className="phone">{card.external_id ?? card.sender ?? "sem contato"}</p>
      <p className="preview">{card.last_message ?? "Sem mensagem ainda"}</p>
      <footer>{messageCountLabel(card.message_count)}</footer>
    </article>
  )
}

export function Column({
  status,
  label,
  hint,
  cards,
  selectedId,
  hot,
  refused,
  onSelect,
  onDragStart,
  onDragEnd,
  onDragOver,
  onDrop,
}: {
  status: Status
  label: string
  hint: string
  cards: TicketCard[]
  selectedId: string | null
  hot: "take" | "refuse" | null
  refused: boolean
  onSelect: (id: string) => void
  onDragStart: (card: TicketCard) => void
  onDragEnd: () => void
  onDragOver: () => void
  onDrop: () => void
}) {
  const tone = hot === "take" ? "is-take" : hot === "refuse" ? "is-refuse-target" : ""
  return (
    <section
      className={["column", tone, refused ? "is-rejected" : ""].filter(Boolean).join(" ")}
      data-status={status}
      onDragOver={(event) => {
        event.preventDefault()
        onDragOver()
      }}
      onDrop={(event) => {
        event.preventDefault()
        onDrop()
      }}
    >
      <header>
        <div>
          <h2>{label}</h2>
          <p>{hint}</p>
        </div>
        <span>{cards.length}</span>
      </header>
      <div className="column-cards">
        {cards.map((card) => (
          <TicketCardView
            key={card.id}
            card={card}
            selected={card.id === selectedId}
            onSelect={onSelect}
            onDragStart={onDragStart}
            onDragEnd={onDragEnd}
          />
        ))}
      </div>
    </section>
  )
}
