import { useCallback, useEffect, useState } from 'react'

export type OsName = 'windows' | 'mac' | 'linux'

/** Backend platform_support dicts (morph/schema/parameters.py) key by OS
 * family string ("darwin", not "mac") -- matches morph.schema.profile.OSInfo. */
export function toBackendFamily(os: OsName): 'windows' | 'darwin' | 'linux' {
  return os === 'mac' ? 'darwin' : os
}

const STORAGE_KEY = 'morph-os-theme'
const OS_ORDER: OsName[] = ['windows', 'mac', 'linux']

function readStored(): OsName {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored === 'windows' || stored === 'mac' || stored === 'linux') return stored
  } catch {
    // localStorage unavailable (private mode, etc.) -- fall through to default.
  }
  return 'windows'
}

export function useOsTheme() {
  const [os, setOsState] = useState<OsName>(readStored)

  useEffect(() => {
    document.documentElement.setAttribute('data-os', os)
    try {
      localStorage.setItem(STORAGE_KEY, os)
    } catch {
      // Non-fatal: just won't persist across reloads.
    }
  }, [os])

  const setOs = useCallback((next: OsName) => setOsState(next), [])

  const cycle = useCallback(() => {
    setOsState((current) => {
      const next = OS_ORDER[(OS_ORDER.indexOf(current) + 1) % OS_ORDER.length]
      return next
    })
  }, [])

  return { os, setOs, cycle }
}
