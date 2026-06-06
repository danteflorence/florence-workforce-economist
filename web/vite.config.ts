import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Customer-facing pricing calculator. Talks to the FastAPI pricing service at
// VITE_API_URL (default localhost:8000 for dev).
export default defineConfig({
  plugins: [react()],
  server: { port: 5179 },
  preview: { port: 5179 },
})
