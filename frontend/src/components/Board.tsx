import { useState } from "react"
import { COLUMNS } from "../labels"
import type { Status, TicketCard, Transitions } from "../types"
import { Column } from "./Column"

export function Board({
  cards,
  transitions,
  selectedId,
  rejected,
  banner,
  onSelect,
  onMove,
}: {
  cards: TicketCard[]
  transitions: Transitions
  selectedId: string | null
  rejected: Status | null
  banner: string | null
  onSelect: (id: string) => void
  onMove: (id: string, target: Status) => void
}) {
  const [dragging, setDragging] = useState<TicketCard | null>(null)
  const [over, setOver] = useState<Status | null>(null)
  const allowed = dragging ? new Set(transitions[dragging.status] ?? []) : null

  return (
    <div className="board-wrap">
      {banner ? (
        <p className="banner" role="alert">
          {banner}
        </p>
      ) : null}
      <div className="board">
        {COLUMNS.map((column) => {
          const columnCards = cards.filter((card) => card.status === column.status)
          let hot: "take" | "refuse" | null = null
          if (dragging && over === column.status && dragging.status !== column.status) {
            hot = allowed?.has(column.status) ? "take" : "refuse"
          }
          return (
            <Column
              key={column.status}
              status={column.status}
              label={column.label}
              hint={column.hint}
              cards={columnCards}
              selectedId={selectedId}
              hot={hot}
              refused={rejected === column.status}
              onSelect={onSelect}
              onDragStart={setDragging}
              onDragEnd={() => {
                setDragging(null)
                setOver(null)
              }}
              onDragOver={() => setOver(column.status)}
              onDrop={() => {
                if (!dragging || dragging.status === column.status) return
                onMove(dragging.id, column.status)
              }}
            />
          )
        })}
      </div>
      <p className="machine">
        Novos → Abertos → Aguardando → Resolvidos → Fechados. Aguardando e Resolvidos podem voltar
        para Abertos. Fechados é terminal. Arrastar para uma coluna fora disso devolve 422.
      </p>
    </div>
  )
}
