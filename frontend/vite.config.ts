import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// The API is proxied under /api and /ws so the browser never needs CORS.
// MORPH_API_PORT lets a second backend run beside the default 8000.
const apiPort = process.env.MORPH_API_PORT ?? '8000'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: `http://127.0.0.1:${apiPort}`,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
      '/ws': {
        target: `ws://127.0.0.1:${apiPort}`,
        ws: true,
      },
    },
  },
})
