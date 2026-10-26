import type { Stage } from "../types"

const STEPS: { id: Stage; index: string; title: string; text: string }[] = [
  { id: "webhook", index: "01", title: "Webhook", text: "POST responde 202 na hora" },
  { id: "queue", index: "02", title: "Fila", text: "ARQ guarda o job no Redis" },
  { id: "worker", index: "03", title: "Worker", text: "Conversa, mensagem e ticket" },
  { id: "board", index: "04", title: "Quadro", text: "O card entra em Novos" },
]

const ORDER: Stage[] = ["webhook", "queue", "worker", "board"]

export function Pipeline({ reached }: { reached: Stage | null }) {
  const hot = reached ? ORDER.indexOf(reached) : -1
  return (
    <ol className="pipeline">
      {STEPS.map((step, index) => (
        <li key={step.id} className={index <= hot ? "is-hot" : undefined} data-step={step.id}>
          <span>{step.index}</span>
          <strong>{step.title}</strong>
          <em>{step.text}</em>
        </li>
      ))}
    </ol>
  )
}
