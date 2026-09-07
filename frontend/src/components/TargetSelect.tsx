import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { PlatformInfo } from '../api/types'
import { updateDraft, useStore } from '../state/store'

const FAMILY_LABEL: Record<string, string> = { darwin: 'macOS', windows: 'Windows', linux: 'Linux' }

/** The run target: which machine (and therefore which OS) every run and
 *  experiment executes on. Reads the real list from /platform. */
export function TargetSelect() {
  const target = useStore((s) => s.draft.target)
  const [platform, setPlatform] = useState<PlatformInfo | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let alive = true
    api
      .getPlatform()
      .then((p) => {
        if (!alive) return
        setPlatform(p)
        const current = p.targets.find((t) => t.id === target)
        if (!current || !current.available) {
          const first = p.targets.find((t) => t.available)
          if (first) updateDraft({ target: first.id })
        }
      })
      .catch(() => alive && setFailed(true))
    return () => {
      alive = false
    }
    // Resolve the target once on mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const current = platform?.targets.find((t) => t.id === target)
  const family = current?.family ?? platform?.host.family ?? ''

  return (
    <label className="target">
      <span className="target__badge" aria-hidden data-family={family}>
        <OsGlyph family={family} />
      </span>
      <span className="sr-only">Run target</span>
      <select
        className="select target__select"
        value={target}
        onChange={(e) => updateDraft({ target: e.target.value })}
        disabled={!platform}
        title={current?.reason ?? current?.label ?? (failed ? 'Could not read run targets' : 'Loading targets')}
      >
        {platform ? (
          platform.targets.map((t) => (
            <option key={t.id} value={t.id} disabled={!t.available}>
              {t.id === 'local' ? `This machine (${FAMILY_LABEL[t.family] ?? t.family})` : t.label}
              {t.available ? '' : ` — ${t.reason ?? 'unavailable'}`}
            </option>
          ))
        ) : (
          <option value="local">{failed ? 'This machine' : 'Loading targets'}</option>
        )}
      </select>
    </label>
  )
}

/** Windows and Linux use the marks under public/icons; macOS is one path. */
function OsGlyph({ family }: { family: string }) {
  if (family === 'linux') return <img src="/icons/linux.svg" width={12} height={12} alt="" />
  if (family === 'windows') return <img src="/icons/windows.svg" width={12} height={12} alt="" />
  if (family === 'darwin')
    return (
      <svg width={12} height={12} viewBox="0 0 20 20" aria-hidden>
        <path
          d="M13.5 2.5c.1 1-.3 2-1 2.7-.7.7-1.7 1.2-2.7 1.1-.1-1 .4-2 1-2.7.7-.7 1.7-1.1 2.7-1.1zM16 14.5c-.4.9-.9 1.7-1.6 2.5-.9 1.1-1.8 2.2-3.2 2.2-1.3 0-1.7-.8-3.3-.8-1.5 0-2 .8-3.3.8-1.3 0-2.3-1.1-3.2-2.3C-.2 14.4-.9 9.9 1 7.4c1-1.4 2.6-2.2 4.1-2.2 1.4 0 2.3.9 3.4.9 1.1 0 1.8-.9 3.4-.9 1.3 0 2.7.7 3.7 1.9-3.2 1.8-2.7 6.2.4 7.4z"
          fill="currentColor"
        />
      </svg>
    )
  return <span className="small">?</span>
}
