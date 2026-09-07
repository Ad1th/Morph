import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'

// `App` owns every route under /app and also answers at `/` for now. When a
// landing page lands it takes `/` here (render <Landing/> when
// window.location.pathname === '/'), and `App` keeps everything under
// routes.ts's APP_BASE untouched.
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
