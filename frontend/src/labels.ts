import type { Status } from "./types"

export const COLUMNS: { status: Status; label: string; hint: string }[] = [
  { status: "new", label: "Novos", hint: "recém-chegados" },
  { status: "open", label: "Abertos", hint: "em atendimento" },
  { status: "waiting_customer", label: "Aguardando", hint: "à espera do cliente" },
  { status: "resolved", label: "Resolvidos", hint: "prontos para fechar" },
  { status: "closed", label: "Fechados", hint: "estado terminal" },
]

export const STATUS_LABEL: Record<Status, string> = {
  new: "Novos",
  open: "Abertos",
  waiting_customer: "Aguardando",
  resolved: "Resolvidos",
  closed: "Fechados",
}

const ACTIONS: Record<string, string> = {
  "new>open": "Assumir",
  "open>waiting_customer": "Aguardar cliente",
  "open>resolved": "Resolver",
  "waiting_customer>open": "Cliente respondeu",
  "waiting_customer>resolved": "Resolver",
  "resolved>closed": "Fechar",
  "resolved>open": "Reabrir",
}

export function actionLabel(from: Status, to: Status): string {
  return ACTIONS[`${from}>${to}`] ?? STATUS_LABEL[to]
}

export function formatClock(iso: string | null | undefined): string {
  if (!iso) return "—"
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return "—"
  return new Intl.DateTimeFormat("pt-BR", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(date)
}

export function messageCountLabel(count: number): string {
  return count === 1 ? "1 mensagem" : `${count} mensagens`
}
