import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'

/* Two entry points share one bundle: the marketing landing page at `/`, and the
   existing product UI at `/app`. A full router would be four dependencies and a
   provider for a two-way split, so the choice is made once here from the path.
   Internal navigation between the two is plain <a href> — a hard load is fine
   and keeps the OS-theme side effects in the app from ever touching the
   landing page. */
const isApp = window.location.pathname.replace(/\/+$/, '').startsWith('/app')
const root = createRoot(document.getElementById('root')!)

const load = isApp
  ? import('./App.tsx').then((m) => m.default)
  : import('./landing/Landing.tsx').then((m) => m.Landing)

load.then((Screen) => {
  root.render(
    <StrictMode>
      <Screen />
    </StrictMode>,
  )
})
