import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import { App } from "./App"
import { Webchat } from "./components/Webchat"
import "./styles.css"

const root = document.getElementById("root")
if (!root) throw new Error("Elemento #root não encontrado")

const path = window.location.pathname.replace(/\/+$/, "") || "/"
const agentDesk = path === "/mesa" || path === "/quadro" || path === "/atendente"

createRoot(root).render(
  <StrictMode>
    {agentDesk ? <App /> : <Webchat />}
  </StrictMode>,
)
