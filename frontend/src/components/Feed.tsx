import { formatClock } from "../labels"
import type { FeedItem } from "../types"

export function Feed({ items, link }: { items: FeedItem[]; link: "connecting" | "live" | "reconnecting" }) {
  return (
    <aside className="feed">
      <header>
        <h2>O que está acontecendo</h2>
        <p>
          {link === "live"
            ? "Stream SSE aberto. Cada etapa do Nível 1 aparece aqui."
            : link === "reconnecting"
              ? "O stream caiu. O browser tenta de novo sozinho."
              : "Abrindo o stream…"}
        </p>
      </header>
      {items.length === 0 ? (
        <p className="feed-empty">
          Dispare um webhook. O 202 volta na hora; o card só nasce quando o worker tira o job da fila.
        </p>
      ) : (
        <ol>
          {items.map((item) => (
            <li key={item.id} data-tone={item.tone}>
              <time dateTime={item.at}>{formatClock(item.at)}</time>
              <div>
                <strong>{item.title}</strong>
                <span>{item.detail}</span>
              </div>
            </li>
          ))}
        </ol>
      )}
    </aside>
  )
}
