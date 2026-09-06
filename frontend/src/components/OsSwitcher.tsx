import { useEffect, useRef, useState } from 'react'
import type { OsName } from '../theme/useOsTheme'
import './OsSwitcher.css'

const LABELS: Record<OsName, string> = {
  windows: 'Windows 11',
  mac: 'macOS',
  linux: 'Linux',
}

export function OsSwitcher({ os, onChange }: { os: OsName; onChange: (os: OsName) => void }) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onClickOutside)
    return () => document.removeEventListener('mousedown', onClickOutside)
  }, [])

  return (
    <div className="os-switcher" ref={ref}>
      <button
        className="os-switcher__badge"
        aria-label={`Switch environment view (current: ${LABELS[os]})`}
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <OsGlyph os={os} />
      </button>
      {open && (
        <div className="os-switcher__menu" role="menu">
          {(Object.keys(LABELS) as OsName[]).map((candidate) => (
            <button
              key={candidate}
              role="menuitem"
              className="os-switcher__item"
              data-active={candidate === os}
              onClick={() => {
                onChange(candidate)
                setOpen(false)
              }}
            >
              <OsGlyph os={candidate} small />
              <span>{LABELS[candidate]}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

function OsGlyph({ os, small }: { os: OsName; small?: boolean }) {
  const size = small ? 16 : 22
  if (os === 'windows') {
    return (
      <svg width={size} height={size} viewBox="0 0 20 20" aria-hidden>
        <rect x="1" y="1" width="8" height="8" fill="#4a7cd4" />
        <rect x="11" y="1" width="8" height="8" fill="#4a7cd4" />
        <rect x="1" y="11" width="8" height="8" fill="#4a7cd4" />
        <rect x="11" y="11" width="8" height="8" fill="#4a7cd4" />
      </svg>
    )
  }
  if (os === 'mac') {
    return (
      <svg width={size} height={size} viewBox="0 0 20 20" aria-hidden>
        <path
          d="M13.5 2.5c.1 1-.3 2-1 2.7-.7.7-1.7 1.2-2.7 1.1-.1-1 .4-2 1-2.7.7-.7 1.7-1.1 2.7-1.1zM16 14.5c-.4.9-.9 1.7-1.6 2.5-.9 1.1-1.8 2.2-3.2 2.2-1.3 0-1.7-.8-3.3-.8-1.5 0-2 .8-3.3.8-1.3 0-2.3-1.1-3.2-2.3C-.2 14.4-.9 9.9 1 7.4c1-1.4 2.6-2.2 4.1-2.2 1.4 0 2.3.9 3.4.9 1.1 0 1.8-.9 3.4-.9 1.3 0 2.7.7 3.7 1.9-3.2 1.8-2.7 6.2.4 7.4z"
          fill="#2b2b2f"
        />
      </svg>
    )
  }
  return (
    <svg width={size} height={size} viewBox="0 0 20 20" aria-hidden>
      <circle cx="10" cy="10" r="9" fill="#0e1116" stroke="#2ee6a6" strokeWidth="1.4" />
      <text x="10" y="14" textAnchor="middle" fontSize="10" fill="#2ee6a6" fontFamily="monospace">
        $
      </text>
    </svg>
  )
}
