import { useState } from 'react'
import type { OsName } from '../theme/useOsTheme'
import './OsSwitcher.css'

/* Plain OS names, no version numbers: "Windows" beside "macOS" and "Linux"
   read as three of the same kind of label. */
const LABELS: Record<OsName, string> = {
  windows: 'Windows',
  mac: 'macOS',
  linux: 'Linux',
}

/* Mirrors OS_ORDER in useOsTheme. Kept here only to name the NEXT skin in the
   button's label and tooltip -- the cycling itself stays in the hook, so the
   two can't disagree about what comes after what. */
const ORDER: OsName[] = ['windows', 'mac', 'linux']

export function OsSwitcher({ os, onCycle }: { os: OsName; onCycle: () => void }) {
  /* Turns accumulate rather than being derived from the current OS. A derived
     angle would have to unwind on the linux -> windows wrap, and a wheel that
     spins backwards to advance reads as undoing the click, not taking it.
     Each turn is a whole revolution, so the art always comes to rest upright:
     pixel art is only crisp at 0 degrees, and a dial parked at 120 would sit
     permanently resampled and jagged. */
  const [turns, setTurns] = useState(0)

  const next = ORDER[(ORDER.indexOf(os) + 1) % ORDER.length]

  return (
    <div className="os-switcher">
      <button
        className="os-switcher__dial"
        /* No menu any more, so no aria-haspopup/expanded: to a screen reader
           this is now what it looks like -- one control that advances. */
        aria-label={`Environment: ${LABELS[os]}. Switch to ${LABELS[next]}.`}
        title={`Switch to ${LABELS[next]}`}
        onClick={() => {
          setTurns((t) => t + 1)
          onCycle()
        }}
      >
        <img
          className="os-switcher__dial-img"
          style={{ transform: `rotate(${turns * 360}deg)` }}
          src="/icons/theme-wheel.png"
          alt=""
          draggable={false}
        />
      </button>
      {/* The whole desktop re-skins, which is unmissable if you can see it.
          This says the same thing to anyone who can't. */}
      <span className="os-switcher__status" role="status" aria-live="polite">
        {LABELS[os]}
      </span>
    </div>
  )
}
