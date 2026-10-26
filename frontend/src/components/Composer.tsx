import { useState } from "react"
import { sendWhatsApp } from "../api"

type Payload = { wamid: string; sender: string; body: string }

export function Composer({
  onAccepted,
  onError,
}: {
  onAccepted: (payload: Payload, resent: boolean) => void
  onError: (message: string) => void
}) {
  const [sender, setSender] = useState("+5511999990001")
  const [body, setBody] = useState("Preciso de ajuda com meu pedido")
  const [last, setLast] = useState<Payload | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(payload: Payload, resent: boolean) {
    setBusy(true)
    onError("")
    try {
      await sendWhatsApp(payload)
      setLast(payload)
      onAccepted(payload, resent)
    } catch (error) {
      onError(error instanceof Error ? error.message : "Falha ao falar com a API")
    } finally {
      setBusy(false)
    }
  }

  return (
    <form
      className="composer"
      onSubmit={(event) => {
        event.preventDefault()
        const payload = { wamid: `wamid.ui.${crypto.randomUUID()}`, sender: sender.trim(), body: body.trim() }
        if (!payload.sender || !payload.body) {
          onError("Informe o número e o texto.")
          return
        }
        void submit(payload, false)
      }}
    >
      <label>
        Número
        <input value={sender} onChange={(event) => setSender(event.target.value)} autoComplete="off" />
      </label>
      <label className="composer-body">
        Mensagem
        <input value={body} onChange={(event) => setBody(event.target.value)} autoComplete="off" />
      </label>
      <div className="composer-actions">
        <button type="submit" disabled={busy}>
          {busy ? "Enviando…" : "Disparar webhook"}
        </button>
        <button
          type="button"
          className="ghost"
          disabled={busy || !last}
          onClick={() => last && void submit(last, true)}
        >
          Reenviar o mesmo wamid
        </button>
      </div>
      <p className="composer-hint">
        O mesmo número reaproveita o ticket enquanto ele não está resolvido ou fechado.
        {last ? <code>{last.wamid}</code> : null}
      </p>
    </form>
  )
}
