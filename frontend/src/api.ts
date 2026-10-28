import type { Board, Status, TicketDetail } from "./types"

const base = import.meta.env.VITE_API_URL ?? ""

export function apiUrl(path: string): string {
  return `${base}${path}`
}

export class ApiError extends Error {
  constructor(message: string) {
    super(message)
    this.name = "ApiError"
  }
}

async function readError(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown }
    if (typeof body.detail === "string") return body.detail
  } catch {
    // The body was not JSON; fall through to the status code.
  }
  return `HTTP ${response.status}`
}

export async function fetchBoard(): Promise<Board> {
  const response = await fetch(apiUrl("/board"))
  if (!response.ok) throw new ApiError(await readError(response))
  return response.json() as Promise<Board>
}

export async function fetchTicket(id: string): Promise<TicketDetail> {
  const response = await fetch(apiUrl(`/tickets/${id}`), { cache: "no-store" })
  if (!response.ok) throw new ApiError(await readError(response))
  return response.json() as Promise<TicketDetail>
}

export async function transitionTicket(
  id: string,
  target: Status,
): Promise<{ status: Status; updated_at: string }> {
  const response = await fetch(apiUrl(`/tickets/${id}/transition`), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ target_status: target }),
  })
  if (!response.ok) throw new ApiError(await readError(response))
  return response.json() as Promise<{ status: Status; updated_at: string }>
}

export async function sendAgentReply(id: string, body: string): Promise<void> {
  const response = await fetch(apiUrl(`/tickets/${id}/messages`), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ body }),
  })
  if (!response.ok) throw new ApiError(await readError(response))
}

export async function sendWebchat(input: { messageId: string; sessionId: string; text: string }): Promise<void> {
  const response = await fetch(apiUrl("/webhooks/webchat"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: input.sessionId,
      message_id: input.messageId,
      text: input.text,
    }),
  })
  if (!response.ok) throw new ApiError(await readError(response))
}

export async function sendWhatsApp(input: { wamid: string; sender: string; body: string }): Promise<void> {
  const response = await fetch(apiUrl("/webhooks/whatsapp"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      object: "whatsapp_business_account",
      entry: [
        {
          id: "dashboard",
          changes: [
            {
              field: "messages",
              value: {
                messaging_product: "whatsapp",
                messages: [
                  {
                    id: input.wamid,
                    from: input.sender,
                    timestamp: String(Math.floor(Date.now() / 1000)),
                    type: "text",
                    text: { body: input.body },
                  },
                ],
              },
            },
          ],
        },
      ],
    }),
  })
  if (!response.ok) throw new ApiError(await readError(response))
}
