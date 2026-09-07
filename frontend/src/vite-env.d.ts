/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Backend base URL when the frontend is deployed separately from the API
   *  (e.g. the static build on Vercel talking to a Morph Fleet worker).
   *  No trailing slash, no /api suffix. Leave unset for local dev and for any
   *  deploy that serves the API same-origin — see .env.example. */
  readonly VITE_API_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
