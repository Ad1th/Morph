import { useRef } from 'react'
import { SCREENS, type ScreenId } from '../routes'
import { Icon, type IconName } from './ui/Icon'

const ICONS: Record<ScreenId, IconName> = {
  projects: 'folder',
  run: 'play',
  experiment: 'flask',
  threshold: 'gauge',
  regressions: 'bookmark',
  environment: 'layers',
}

/** Left navigation. Arrow keys move between items; Home/End jump. */
export function Rail({ active, onNavigate }: { active: ScreenId; onNavigate: (s: ScreenId) => void }) {
  const listRef = useRef<HTMLUListElement>(null)

  function onKey(e: React.KeyboardEvent) {
    const items = Array.from(listRef.current?.querySelectorAll<HTMLAnchorElement>('a') ?? [])
    const idx = items.findIndex((el) => el === document.activeElement)
    if (idx < 0) return
    let next = idx
    if (e.key === 'ArrowDown' || e.key === 'ArrowRight') next = (idx + 1) % items.length
    else if (e.key === 'ArrowUp' || e.key === 'ArrowLeft') next = (idx - 1 + items.length) % items.length
    else if (e.key === 'Home') next = 0
    else if (e.key === 'End') next = items.length - 1
    else return
    e.preventDefault()
    items[next].focus()
  }

  return (
    <nav className="rail" aria-label="Screens">
      <a className="rail__brand" href="/app/projects" onClick={(e) => (e.preventDefault(), onNavigate('projects'))}>
        Morph
      </a>
      <ul className="rail__list" ref={listRef} onKeyDown={onKey}>
        {SCREENS.map((s) => (
          <li key={s.id}>
            <a
              href={`/app/${s.id}`}
              className="rail__item"
              aria-current={active === s.id ? 'page' : undefined}
              onClick={(e) => {
                e.preventDefault()
                onNavigate(s.id)
              }}
            >
              <Icon name={ICONS[s.id]} size={16} />
              <span className="rail__label">
                {s.label}
                <span className="rail__hint">{s.hint}</span>
              </span>
            </a>
          </li>
        ))}
      </ul>
      <p className="rail__foot faint small">Now it breaks on your machine too.</p>
    </nav>
  )
}
