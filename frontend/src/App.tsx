import { useCallback, useEffect, useRef, useState } from "react"
import { ApiError, apiUrl, fetchBoard, transitionTicket } from "./api"
import { Board } from "./components/Board"
import { Composer } from "./components/Composer"
import { Desk } from "./components/Desk"
import { Drawer } from "./components/Drawer"
import { Feed } from "./components/Feed"
import { Pipeline } from "./components/Pipeline"
import { interpret } from "./interpret"
import type { FeedItem, HubEvent, Stage, Status, TicketCard, Transitions } from "./types"

type LinkState = "connecting" | "live" | "reconnecting"

export function App() {
  const [cards, setCards] = useState<TicketCard[]>([])
  const [transitions, setTransitions] = useState<Transitions>({})
  const [feed, setFeed] = useState<FeedItem[]>([])
  const [link, setLink] = useState<LinkState>("connecting")
  const [spotlight, setSpotlight] = useState<{ stage: Stage; token: number } | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [banner, setBanner] = useState<string | null>(null)
  const [rejected, setRejected] = useState<Status | null>(null)
  const [bootError, setBootError] = useState<string | null>(null)
  const [view, setView] = useState<"mesa" | "quadro">("mesa")
  const [focusKey, setFocusKey] = useState<string | null>(null)
  const applyRef = useRef<(event: HubEvent) => void>(() => {})

  const pushFeed = useCallback((item: Omit<FeedItem, "id">) => {
    setFeed((prev) => [{ ...item, id: crypto.randomUUID() }, ...prev].slice(0, 48))
  }, [])

  const upsert = useCallback((card: TicketCard) => {
    setCards((prev) => {
      const index = prev.findIndex((item) => item.id === card.id)
      if (index === -1) return [card, ...prev]
      const next = prev.slice()
      next[index] = card
      return next
    })
  }, [])

  const light = useCallback((stage: Stage) => {
    setSpotlight({ stage, token: Date.now() })
  }, [])

  const loadBoard = useCallback(async () => {
    const board = await fetchBoard()
    setCards(board.tickets)
    setTransitions(board.transitions)
    setBootError(null)
  }, [])

  applyRef.current = (event) => {
    const next = interpret(event)
    if (!next) return
    if (next.stage) light(next.stage)
    if (next.card) upsert(next.card)
    pushFeed({ tone: next.tone, title: next.title, detail: next.detail, at: next.at })
  }

  useEffect(() => {
    loadBoard().catch((reason: unknown) => {
      setBootError(reason instanceof Error ? reason.message : "A API não respondeu")
    })
  }, [loadBoard])

  useEffect(() => {
    if (!spotlight) return
    const timer = window.setTimeout(() => setSpotlight(null), 3200)
    return () => window.clearTimeout(timer)
  }, [spotlight])

  useEffect(() => {
    const source = new EventSource(apiUrl("/events"))
    source.onopen = () => {
      setLink("live")
      loadBoard().catch(() => undefined)
    }
    source.onerror = () => setLink("reconnecting")
    source.onmessage = (message) => {
      try {
        applyRef.current(JSON.parse(message.data) as HubEvent)
      } catch {
        // Ignore a malformed frame; the next event still arrives on this connection.
      }
    }
    return () => source.close()
  }, [loadBoard])

  useEffect(() => {
    if (!rejected) return
    const timer = window.setTimeout(() => setRejected(null), 900)
    return () => window.clearTimeout(timer)
  }, [rejected])

  useEffect(() => {
    if (!focusKey) return
    const match = cards
      .filter((card) => `${card.channel}:${card.external_id}` === focusKey)
      .sort((a, b) => (b.updated_at ?? "").localeCompare(a.updated_at ?? ""))[0]
    if (!match) return
    setSelectedId(match.id)
    setFocusKey(null)
  }, [cards, focusKey])

  async function move(id: string, target: Status) {
    setBanner(null)
    try {
      const updated = await transitionTicket(id, target)
      setCards((prev) =>
        prev.map((card) =>
          card.id === id ? { ...card, status: updated.status, updated_at: updated.updated_at } : card,
        ),
      )
    } catch (reason) {
      const detail = reason instanceof ApiError ? reason.message : "Falha ao mover o ticket"
      setBanner(`Transição recusada. ${detail}`)
      setRejected(target)
    }
  }

  const selected = cards.find((card) => card.id === selectedId) ?? null
  const closeDrawer = useCallback(() => setSelectedId(null), [])

  return (
    <div className={view === "mesa" ? "app is-desk" : "app"}>
      <header className="top">
        <div className="brand">
          <span className="mark" aria-hidden="true">
            <i />
            <i />
            <i />
            <i />
          </span>
          <div>
            <p className="eyebrow">Atendimento omnichannel</p>
            <h1>Omnihub</h1>
          </div>
        </div>
        <div className="view-switch" role="tablist">
          <button type="button" className={view === "mesa" ? "chip is-on" : "chip"} onClick={() => setView("mesa")}>
            Mesa
          </button>
          <button type="button" className={view === "quadro" ? "chip is-on" : "chip"} onClick={() => setView("quadro")}>
            Quadro
          </button>
        </div>
        <p className={`link link-${link}`}>
          <i />
          {link === "live" ? "SSE ao vivo" : link === "reconnecting" ? "Reconectando" : "Conectando"}
        </p>
      </header>

      {view === "mesa" ? (
        <Desk
          cards={cards}
          transitions={transitions}
          selectedId={selectedId}
          latest={feed[0] ?? null}
          onSelect={setSelectedId}
          onMove={(id, target) => void move(id, target)}
          onSimulated={(channel, externalId) => {
            light("webhook")
            setFocusKey(`${channel}:${externalId}`)
          }}
        />
      ) : (
        <>
      <Composer
        onAccepted={(payload, resent) => {
          light("webhook")
          pushFeed({
            tone: "http",
            title: resent ? "Webhook reenviado · 202" : "Webhook aceito · 202",
            detail: resent
              ? `${payload.wamid} de novo. Se já foi gravado, para no webhook; se o job ainda estava na fila, o worker segura.`
              : `${payload.sender} · ${payload.body}`,
            at: new Date().toISOString(),
          })
        }}
        onError={(message) => setBanner(message || null)}
      />

      <Pipeline reached={spotlight?.stage ?? null} />

      <main className={selected ? "workspace with-drawer" : "workspace"}>
        <Board
          cards={cards}
          transitions={transitions}
          selectedId={selectedId}
          rejected={rejected}
          banner={banner ?? (bootError ? `Não consegui carregar o quadro. ${bootError}` : null)}
          onSelect={(id) => setSelectedId((current) => (current === id ? null : id))}
          onMove={(id, target) => void move(id, target)}
        />
        <Feed items={feed} link={link} />
        {selected ? (
          <Drawer card={selected} transitions={transitions} onClose={closeDrawer} onMove={(id, target) => void move(id, target)} />
        ) : null}
      </main>
        </>
      )}
    </div>
  )
}
