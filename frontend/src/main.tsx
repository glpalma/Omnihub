import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import { App } from "./App"
import { Webchat } from "./components/Webchat"
import "./styles.css"

const root = document.getElementById("root")
if (!root) throw new Error("Elemento #root não encontrado")

const path = window.location.pathname.replace(/\/+$/, "") || "/"

createRoot(root).render(
  <StrictMode>
    {path === "/chat" ? <Webchat /> : <App />}
  </StrictMode>,
)
