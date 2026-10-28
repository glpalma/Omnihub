export type Status = "bot" | "new" | "open" | "waiting_customer" | "resolved" | "closed"

export type TicketCard = {
  id: string
  conversation_id: string
  status: Status
  channel: string | null
  external_id: string | null
  sender: string | null
  last_message: string | null
  last_external_message_id: string | null
  message_count: number
  created_at: string | null
  updated_at: string | null
}

export type Transitions = Partial<Record<Status, Status[]>>

export type Board = {
  tickets: TicketCard[]
  transitions: Transitions
}

export type TicketMessage = {
  id: string
  external_message_id: string
  channel: string
  direction: string
  body: string
  sender: string
  created_at: string
}

export type TicketDetail = TicketCard & {
  messages: TicketMessage[]
}

export type HubEvent =
  | { type: "hello"; at?: string }
  | {
      type: "job.queued"
      at?: string
      channel: string
      external_message_id: string
      sender: string
      body: string
    }
  | { type: "webhook.duplicate"; at?: string; external_message_id: string; sender: string }
  | { type: "ticket.created"; at?: string; external_message_id: string; ticket: TicketCard }
  | { type: "message.appended"; at?: string; external_message_id: string; ticket: TicketCard }
  | { type: "message.sent"; at?: string; external_message_id: string; ticket: TicketCard }
  | { type: "message.duplicate"; at?: string; external_message_id: string; sender: string }
  | {
      type: "ticket.transitioned"
      at?: string
      from_status: Status
      to_status: Status
      ticket: TicketCard
    }

export type FeedTone = "http" | "queue" | "worker" | "board" | "warn" | "state"

export type FeedItem = {
  id: string
  at: string
  tone: FeedTone
  title: string
  detail: string
}

export type Stage = "webhook" | "queue" | "worker" | "board"
