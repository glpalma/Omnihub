import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

const target = process.env.API_PROXY_TARGET ?? "http://localhost:8000"

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    proxy: {
      "/board": target,
      "/events": { target, changeOrigin: true },
      "/tickets": target,
      "/webhooks": target,
      "/health": target,
    },
  },
})
