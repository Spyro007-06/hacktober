import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { '/api': 'http://localhost:8000' },
    // Phones reach the dev server through a Cloudflare Tunnel HTTPS link (mic needs a secure context).
    allowedHosts: ['.trycloudflare.com'],
  },
})
