// Route table for the app. `/` and `/app` both resolve to the app so a landing
// page can later claim `/` in main.tsx without touching anything here.
import { useCallback, useEffect, useState } from 'react'

export const APP_BASE = '/app'

export type ScreenId = 'projects' | 'run' | 'experiment' | 'threshold' | 'regressions' | 'environment'

export const SCREENS: { id: ScreenId; label: string; hint: string }[] = [
  { id: 'projects', label: 'Projects', hint: 'Choose what to run' },
  { id: 'run', label: 'Run', hint: 'Set conditions, run once' },
  { id: 'experiment', label: 'Experiment', hint: 'Isolate the cause' },
  { id: 'threshold', label: 'Threshold', hint: 'Find where it breaks' },
  { id: 'regressions', label: 'Regressions', hint: 'Keep it from coming back' },
  { id: 'environment', label: 'Environment', hint: 'Capture and compare' },
]

export const DEFAULT_SCREEN: ScreenId = 'projects'

export function pathFor(screen: ScreenId): string {
  return `${APP_BASE}/${screen}`
}

export function resolveScreen(pathname: string): ScreenId {
  const trimmed = pathname.replace(/\/+$/, '')
  const rest = trimmed.startsWith(APP_BASE) ? trimmed.slice(APP_BASE.length) : trimmed
  const seg = rest.split('/').filter(Boolean)[0]
  return SCREENS.some((s) => s.id === seg) ? (seg as ScreenId) : DEFAULT_SCREEN
}

/** History-based router: the URL is the source of truth, browser Back works,
 *  and a refresh lands on the same screen. */
export function useRoute() {
  const [screen, setScreen] = useState<ScreenId>(() => resolveScreen(window.location.pathname))

  useEffect(() => {
    const onPop = () => setScreen(resolveScreen(window.location.pathname))
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [])

  const navigate = useCallback((next: ScreenId) => {
    const path = pathFor(next)
    if (window.location.pathname !== path) window.history.pushState(null, '', path)
    setScreen(next)
    window.scrollTo({ top: 0 })
  }, [])

  return { screen, navigate }
}
