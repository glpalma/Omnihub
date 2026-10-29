type Vision = "atendente" | "cliente"

export function VisionSwitch({ current }: { current: Vision }) {
  return (
    <div className="vision-switch" role="tablist" aria-label="Visão">
      <a className={current === "atendente" ? "chip is-on" : "chip"} href="/mesa" role="tab" aria-selected={current === "atendente"}>
        Visão do atendente
      </a>
      <a className={current === "cliente" ? "chip is-on" : "chip"} href="/" role="tab" aria-selected={current === "cliente"}>
        Visão do cliente
      </a>
    </div>
  )
}
