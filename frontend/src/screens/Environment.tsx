import { useCallback, useEffect, useMemo, useState } from 'react'
import { api, errorMessage } from '../api/client'
import { getField } from '../api/profileFields'
import type { EnvironmentProfile, ParameterMetadata, SavedProfileRef } from '../api/types'
import { CodeBlock } from '../components/ui/CodeBlock'
import { Dialog } from '../components/ui/Dialog'
import { Icon } from '../components/ui/Icon'
import { StateChip } from '../components/ui/Chips'
import { fmtValue } from '../lib/format'
import { formatSummary } from '../lib/summary'
import type { ScreenId } from '../routes'
import { useRunDraft } from '../state/useRunDraft'
import './screens.css'

type Side = 'left' | 'right'
type Source = { kind: 'host' } | { kind: 'draft' } | { kind: 'saved'; id: string }

const ALWAYS = ['os.family', 'os.version', 'cpu.architecture', 'cpu.cores', 'cpu.logical_processors', 'memory.total_mb', 'locale.locale', 'locale.timezone', 'network.latency_ms', 'network.packet_loss_percent']

export function Environment({ onNavigate }: { onNavigate: (s: ScreenId) => void }) {
  const { draft, capture, capturing, setProfile } = useRunDraft()
  const [catalog, setCatalog] = useState<Record<string, ParameterMetadata> | null>(null)
  const [saved, setSaved] = useState<SavedProfileRef[]>([])
  const [loaded, setLoaded] = useState<Record<string, EnvironmentProfile>>({})
  const [left, setLeft] = useState<Source>({ kind: 'host' })
  const [right, setRight] = useState<Source>({ kind: 'draft' })
  const [error, setError] = useState<string | null>(null)
  const [saveOpen, setSaveOpen] = useState(false)
  const [showAll, setShowAll] = useState(false)
  const [jsonOpen, setJsonOpen] = useState(false)

  const refresh = useCallback(() => {
    api.listProfiles().then(setSaved).catch((err) => setError(errorMessage(err)))
  }, [])

  useEffect(() => {
    refresh()
    api.getParameterCatalog().then(setCatalog).catch((err) => setError(errorMessage(err)))
  }, [refresh])

  const resolve = useCallback(
    (s: Source): EnvironmentProfile | null => {
      if (s.kind === 'host') return draft.hostProfile
      if (s.kind === 'draft') return draft.profile
      return loaded[s.id] ?? null
    },
    [draft.hostProfile, draft.profile, loaded],
  )

  async function ensureLoaded(id: string) {
    if (loaded[id]) return
    try {
      const p = await api.getProfile(id)
      setLoaded((l) => ({ ...l, [id]: p }))
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  function choose(side: Side, value: string) {
    const src: Source = value === 'host' ? { kind: 'host' } : value === 'draft' ? { kind: 'draft' } : { kind: 'saved', id: value }
    if (src.kind === 'saved') void ensureLoaded(src.id)
    ;(side === 'left' ? setLeft : setRight)(src)
  }

  const key = (s: Source) => (s.kind === 'saved' ? s.id : s.kind)
  const label = (s: Source) => (s.kind === 'host' ? 'This machine (captured)' : s.kind === 'draft' ? 'Run draft (target)' : `Saved: ${s.id}`)

  const a = resolve(left)
  const b = resolve(right)

  const rows = useMemo(() => {
    if (!catalog) return []
    const paths = new Set<string>(ALWAYS)
    Object.values(catalog).forEach((m) => paths.add(m.field_path))
    return Array.from(paths).map((path) => {
      const meta = Object.values(catalog).find((m) => m.field_path === path)
      const fa = a ? getField(a, path) : undefined
      const fb = b ? getField(b, path) : undefined
      const va = fa?.value
      const vb = fb?.value
      const differs = JSON.stringify(va ?? null) !== JSON.stringify(vb ?? null)
      return { path, name: meta?.name ?? path.split('.').slice(-1)[0].replace(/_/g, ' '), unit: meta?.unit ?? '', va, vb, sa: fa?.status, sb: fb?.status, differs }
    })
  }, [catalog, a, b])

  const visible = rows.filter((r) => showAll || r.differs || (r.va == null && r.vb == null ? false : false))
  const diffCount = rows.filter((r) => r.differs).length

  return (
    <>
      <header className="page__head">
        <div>
          <h1>Environment</h1>
          <p>Capture this machine, keep profiles you care about, and see exactly what differs between two of them.</p>
        </div>
        <div className="page__actions">
          <button className="btn" onClick={() => capture(false)} disabled={capturing}>
            <Icon name="refresh" size={14} /> {capturing ? 'Capturing…' : 'Capture again'}
          </button>
          <button className="btn" onClick={() => setSaveOpen(true)} disabled={!draft.profile}>
            <Icon name="bookmark" size={14} /> Save draft as profile
          </button>
        </div>
      </header>

      {error && (
        <p className="note" data-tone="fail" role="alert">
          <Icon name="alert" />
          <span>{error}</span>
        </p>
      )}

      <section className="env-pick">
        {(['left', 'right'] as Side[]).map((side) => {
          const src = side === 'left' ? left : right
          const prof = side === 'left' ? a : b
          return (
            <div className="env-pick__col" key={side}>
              <div className="field">
                <label htmlFor={`env-${side}`}>{side === 'left' ? 'Compare' : 'with'}</label>
                <select id={`env-${side}`} className="select" value={key(src)} onChange={(e) => choose(side, e.target.value)}>
                  <option value="host">This machine (captured)</option>
                  <option value="draft">Run draft (target)</option>
                  {saved.map((s) => (
                    <option key={s.id} value={s.id}>
                      Saved: {s.id}
                    </option>
                  ))}
                </select>
              </div>
              <p className="small muted env-pick__summary">{prof ? formatSummary(prof) || 'nothing set' : 'not loaded'}</p>
              {src.kind === 'saved' && prof && (
                <button className="btn btn--sm" onClick={() => { setProfile(structuredClone(prof)); onNavigate('run') }}>
                  Load into the run draft
                </button>
              )}
            </div>
          )
        })}
      </section>

      <section className="section">
        <div className="section__head">
          <h2>
            {diffCount === 0 ? 'No differences' : `${diffCount} difference${diffCount === 1 ? '' : 's'}`}
          </h2>
          <div className="row">
            <label className="toggle">
              <input type="checkbox" checked={showAll} onChange={(e) => setShowAll(e.target.checked)} />
              <span className="small">Show unchanged rows</span>
            </label>
            <button className="btn btn--ghost btn--sm" onClick={() => setJsonOpen((v) => !v)} aria-expanded={jsonOpen}>
              JSON
            </button>
          </div>
        </div>
        {!catalog ? (
          <p className="muted">Loading the parameter catalog…</p>
        ) : (
          <div className="table-wrap">
            <table className="table diff">
              <thead>
                <tr>
                  <th>Parameter</th>
                  <th>{label(left)}</th>
                  <th>{label(right)}</th>
                </tr>
              </thead>
              <tbody>
                {visible.length === 0 && (
                  <tr>
                    <td colSpan={3} className="muted">
                      {showAll ? 'No parameters to show.' : 'The two profiles agree on every parameter.'}
                    </td>
                  </tr>
                )}
                {visible.map((r) => (
                  <tr key={r.path} data-differs={r.differs}>
                    <td>
                      {r.name}
                      <div className="faint small">{r.path}</div>
                    </td>
                    <td>
                      <span className="diff__val">{fmtValue(r.va, r.unit)}</span>
                      {r.sa && r.sa !== 'captured' && r.sa !== 'requested' && (
                        <>
                          {' '}
                          <StateChip status={r.sa} />
                        </>
                      )}
                    </td>
                    <td>
                      <span className="diff__val" data-changed={r.differs}>
                        {r.differs && <Icon name="arrowRight" size={12} />}
                        {fmtValue(r.vb, r.unit)}
                      </span>
                      {r.sb && r.sb !== 'captured' && (
                        <>
                          {' '}
                          <StateChip status={r.sb} />
                        </>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {jsonOpen && b && (
          <div style={{ marginTop: 'var(--s-3)' }}>
            <CodeBlock code={JSON.stringify(b, null, 2)} filename={`${label(right)} · profile JSON`} maxHeight={360} />
          </div>
        )}
      </section>

      <section className="section">
        <div className="section__head">
          <h2>Saved profiles</h2>
          <span className="small muted">.morph/profiles</span>
        </div>
        {saved.length === 0 ? (
          <p className="muted small">None yet. Save the run draft to reuse it later or share it.</p>
        ) : (
          <ul className="env-saved">
            {saved.map((s) => (
              <li key={s.id}>
                <span>{s.id}</span>
                <span className="faint small">{s.path}</span>
                <button
                  className="btn btn--sm"
                  onClick={async () => {
                    await ensureLoaded(s.id)
                    setRight({ kind: 'saved', id: s.id })
                  }}
                >
                  Compare
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <SaveProfileDialog
        open={saveOpen}
        onClose={() => setSaveOpen(false)}
        profile={draft.profile}
        onSaved={() => {
          setSaveOpen(false)
          refresh()
        }}
      />
    </>
  )
}

function SaveProfileDialog({ open, onClose, profile, onSaved }: { open: boolean; onClose: () => void; profile: EnvironmentProfile | null; onSaved: () => void }) {
  const [id, setId] = useState('')
  const [desc, setDesc] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const valid = /^[A-Za-z0-9._-]{1,64}$/.test(id)

  async function save() {
    if (!profile) return
    setBusy(true)
    setErr(null)
    try {
      await api.saveProfile(id, profile, desc || undefined)
      onSaved()
    } catch (e) {
      setErr(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onClose={onClose} title="Save profile">
      <div className="field">
        <label htmlFor="prof-id">Name</label>
        <input id="prof-id" className="input" value={id} onChange={(e) => setId(e.target.value)} placeholder="flaky-3g" aria-invalid={id !== '' && !valid} spellCheck={false} />
      </div>
      <div className="field">
        <label htmlFor="prof-desc">Description (optional)</label>
        <input id="prof-desc" className="input" value={desc} onChange={(e) => setDesc(e.target.value)} />
      </div>
      {err && <p className="field__error">{err}</p>}
      <div className="row" style={{ justifyContent: 'flex-end' }}>
        <button className="btn btn--ghost" onClick={onClose}>
          Cancel
        </button>
        <button className="btn btn--primary" onClick={save} disabled={!valid || busy || !profile}>
          {busy ? 'Saving…' : 'Save'}
        </button>
      </div>
    </Dialog>
  )
}
