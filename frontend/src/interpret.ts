import { STATUS_LABEL } from "./labels"
import type { FeedTone, HubEvent, Stage, TicketCard } from "./types"

export type Interpretation = {
  tone: FeedTone
  title: string
  detail: string
  at: string
  card?: TicketCard
  stage?: Stage
}

function atOf(event: { at?: string }): string {
  return event.at ?? new Date().toISOString()
}

export function interpret(event: HubEvent): Interpretation | null {
  switch (event.type) {
    case "hello":
      return null
    case "job.queued":
      return {
        tone: "queue",
        title: "Job na fila Redis",
        detail: `${event.sender} · ${event.body}`,
        at: atOf(event),
        stage: "queue",
      }
    case "webhook.duplicate":
      return {
        tone: "warn",
        title: "Webhook segurou o wamid",
        detail: `${event.external_message_id} já estava no banco. A fila não recebeu outro job.`,
        at: atOf(event),
        stage: "webhook",
      }
    case "ticket.created":
      return {
        tone: "board",
        title: "Worker criou o ticket em Novos",
        detail: `${event.ticket.sender ?? "contato"} · ${event.ticket.last_message ?? ""}`,
        at: atOf(event),
        card: event.ticket,
        stage: "board",
      }
    case "message.appended":
      return {
        tone: "worker",
        title: "Mensagem entrou no ticket que já existia",
        detail: `${event.ticket.sender ?? "contato"} · ${event.ticket.last_message ?? ""}`,
        at: atOf(event),
        card: event.ticket,
        stage: "worker",
      }
    case "message.sent":
      return {
        tone: "state",
        title: "Atendente respondeu",
        detail: event.ticket.last_message ?? "",
        at: atOf(event),
        card: event.ticket,
      }
    case "message.duplicate":
      return {
        tone: "warn",
        title: "Worker segurou o wamid",
        detail: `${event.external_message_id} já tinha sido gravado. A constraint impediu a duplicata.`,
        at: atOf(event),
        stage: "worker",
      }
    case "ticket.transitioned":
      return {
        tone: "state",
        title: "Transição aceita",
        detail: `${STATUS_LABEL[event.from_status]} → ${STATUS_LABEL[event.to_status]} · ${event.ticket.sender ?? event.ticket.external_id ?? "ticket"}`,
        at: atOf(event),
        card: event.ticket,
      }
    default:
      return null
  }
}
