import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Standalone site — no proxy to the API/app, this is the public marketing page.
export default defineConfig({
  plugins: [react()],
})
