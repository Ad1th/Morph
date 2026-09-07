import { useEffect, useMemo, useState } from 'react'
import { ApiError, api, errorMessage } from '../api/client'
import { getField } from '../api/profileFields'
import type { EnvironmentProfile, FidelityEntry, FieldStatus, ParameterMetadata, RunResult } from '../api/types'
import { EnvVarsEditor } from '../components/EnvVarsEditor'
import { ParamGroup } from '../components/ParamGroup'
import { PARAM_GROUPS } from '../components/paramGroups'
import { ParameterRow } from '../components/ParameterRow'
import { Chip, StateChip } from '../components/ui/Chips'
import { CodeBlock } from '../components/ui/CodeBlock'
import { Icon } from '../components/ui/Icon'
import { fmtMs, fmtValue } from '../lib/format'
import { formatSummary, requestedPaths } from '../lib/summary'
import type { ScreenId } from '../routes'
import { setState, useStore } from '../state/store'
import { PRESETS, resolveMax, useRunDraft } from '../state/useRunDraft'
import './screens.css'

type Phase = 'idle' | 'reconciling' | 'running' | 'done' | 'setup-error' | 'error'

/** Last JSON line of stdout per the apps/ contract, if there is one. */
function structuredOutcome(stdout: string): Record<string, unknown> | null {
  const lines = stdout.trim().split('\n').reverse()
  for (const line of lines.slice(0, 5)) {
    const t = line.trim()
    if (!t.startsWith('{')) continue
    try {
      return JSON.parse(t) as Record<string, unknown>
    } catch {
      /* keep looking */
    }
  }
  return null
}

export function Run({ onNavigate }: { onNavigate: (s: ScreenId) => void }) {
  const { draft, capturing, captureError, capture, setField, resetField, setProfile, choosePreset, set } = useRunDraft()
  const lastRun = useStore((s) => s.lastRun)
  const [catalog, setCatalog] = useState<Record<string, ParameterMetadata> | null>(null)
  const [catalogError, setCatalogError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [phase, setPhase] = useState<Phase>('idle')
  const [reconciled, setReconciled] = useState<EnvironmentProfile | null>(null)
  const [fidelity, setFidelity] = useState<Record<string, FidelityEntry> | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [detailsOpen, setDetailsOpen] = useState(false)
  const [outputTab, setOutputTab] = useState<'stdout' | 'stderr'>('stdout')

  useEffect(() => {
    api.getParameterCatalog().then(setCatalog).catch((err) => setCatalogError(errorMessage(err)))
  }, [])

  const profile = draft.profile
  const host = draft.hostProfile
  const family = host?.os?.family?.value ?? 'linux'
  const summary = useMemo(() => (profile ? formatSummary(profile, host) : ''), [profile, host])
  const changed = useMemo(() => (profile ? requestedPaths(profile) : []), [profile])
  const filter = search.trim().toLowerCase()

  async function reconcile() {
    if (!profile) return null
    setPhase('reconciling')
    setError(null)
    try {
      const [r, f] = await Promise.all([
        api.reconcileProfile(profile),
        api.profileFidelity(profile).catch(() => null),
      ])
      setReconciled(r)
      setFidelity(f)
      setPhase((p) => (p === 'reconciling' ? 'idle' : p))
      return r
    } catch (err) {
      setError(errorMessage(err))
      setPhase('error')
      return null
    }
  }

  async function runOnce() {
    if (!profile || !draft.command.trim()) return
    const r = await reconcile()
    if (!r) return
    setPhase('running')
    try {
      const result = await api.run({
        command: draft.command.trim(),
        profile,
        cwd: draft.cwd,
        target: draft.target,
        timeout: draft.timeoutSec,
      })
      setState({ lastRun: result })
      setPhase('done')
      setOutputTab(result.passed || result.stderr.trim() === '' ? 'stdout' : 'stderr')
    } catch (err) {
      setError(errorMessage(err))
      setPhase(err instanceof ApiError && err.isSetupError ? 'setup-error' : 'error')
    }
  }

  const canRun = Boolean(profile && draft.command.trim()) && phase !== 'running' && phase !== 'reconciling'

  return (
    <>
      <header className="page__head">
        <div>
          <h1>Run</h1>
          <p>Set the conditions, then run the command once under them. Every field says whether Morph reproduced it or only approximated it.</p>
        </div>
      </header>

      {captureError && (
        <p className="note" data-tone="fail" role="alert">
          <Icon name="alert" />
          <span>{captureError}</span>
          <button className="btn btn--sm" onClick={() => capture(true)}>
            Retry capture
          </button>
        </p>
      )}
      {catalogError && (
        <p className="note" data-tone="fail" role="alert">
          <Icon name="alert" />
          <span>{catalogError}</span>
        </p>
      )}

      <div className="run-layout">
        <div className="run-main">
          {/* command */}
          <section className="run-command">
            <div className="field">
              <label htmlFor="run-command">Command</label>
              <input
                id="run-command"
                className="input"
                value={draft.command}
                onChange={(e) => set({ command: e.target.value })}
                placeholder={draft.project ? 'No entry point detected; type the command' : 'Connect a project first, or type a command'}
                spellCheck={false}
              />
              <span className="field__help">
                {draft.project ? (
                  <>
                    in <code className="inline-code">{draft.cwd ?? draft.project.path}</code>
                  </>
                ) : (
                  <button className="link-btn" onClick={() => onNavigate('projects')}>
                    Connect a project
                  </button>
                )}
              </span>
            </div>
          </section>

          {/* presets + search */}
          <div className="run-toolbar">
            <div className="field">
              <label htmlFor="preset">Preset</label>
              <select id="preset" className="select" value={draft.presetName ?? ''} onChange={(e) => e.target.value && choosePreset(e.target.value)}>
                <option value="">{draft.presetName ? '' : 'Custom'}</option>
                {PRESETS.map((p) => (
                  <option key={p.id} value={p.id} title={p.hint}>
                    {p.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="field run-toolbar__search">
              <label htmlFor="param-search">Find a parameter</label>
              <input id="param-search" className="input" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="latency, cores, locale…" />
            </div>
            <div className="run-toolbar__actions">
              <button className="btn" onClick={() => capture(true)} disabled={capturing}>
                <Icon name="refresh" size={14} />
                {capturing ? 'Detecting…' : 'Reset to detected'}
              </button>
            </div>
          </div>

          {!profile || !catalog ? (
            <p className="muted" role="status">
              {capturing ? 'Detecting this machine…' : 'Waiting for the host profile.'}
            </p>
          ) : (
            <div className="pgroups">
              {PARAM_GROUPS.map((group) => {
                const keys = group.keys.filter((key) => {
                  const meta = catalog[key]
                  if (!meta) return false
                  if (!filter) return true
                  return meta.name.toLowerCase().includes(filter) || meta.field_path.includes(filter)
                })
                if (keys.length === 0) return null
                const groupChanged = group.keys.filter((k) => catalog[k] && changed.includes(catalog[k].field_path)).length
                return (
                  <ParamGroup key={group.name} name={group.name} changed={groupChanged} defaultOpen={group.name === 'Network' || Boolean(filter)}>
                    {keys.map((key) => {
                      const meta = catalog[key]
                      const field = getField(profile, meta.field_path)
                      const reconciledStatus = reconciled ? getField(reconciled, meta.field_path)?.status : undefined
                      return (
                        <ParameterRow
                          key={key}
                          meta={meta}
                          field={
                            field && reconciledStatus && field.status === 'requested'
                              ? { ...field, status: reconciledStatus as FieldStatus }
                              : field
                          }
                          max={resolveMax(meta, host, profile)}
                          support={meta.platform_support[family] ?? 'unsupported'}
                          statusDetail={fidelity?.[meta.field_path] ? `${fidelity[meta.field_path].mechanism ?? ''}${fidelity[meta.field_path].detail ? `: ${fidelity[meta.field_path].detail}` : ''}` : undefined}
                          hostValue={host ? getField(host, meta.field_path)?.value : undefined}
                          onChange={(v) => setField(meta.field_path, v)}
                          onReset={() => resetField(meta.field_path)}
                        />
                      )
                    })}
                  </ParamGroup>
                )
              })}
              {(!filter || 'environment variables'.includes(filter)) && (
                <ParamGroup name="Environment variables" changed={Object.keys(profile.env_vars).length}>
                  <EnvVarsEditor vars={profile.env_vars} onChange={(env_vars) => setProfile({ ...profile, env_vars })} />
                </ParamGroup>
              )}
            </div>
          )}
        </div>

        <aside className="run-side">
          <div className="run-side__sticky">
            <section className="card">
              <h2 className="run-side__title">Target environment</h2>
              <p className="run-summary">{summary || 'Everything at this machine’s detected values.'}</p>
              {changed.length > 0 && catalog && (
                <ul className="run-changes">
                  {changed.map((path) => {
                    const meta = Object.values(catalog).find((m) => m.field_path === path)
                    const f = getField(profile!, path)
                    const rs = reconciled ? getField(reconciled, path)?.status : undefined
                    const fd = fidelity?.[path]
                    return (
                      <li key={path}>
                        <span>{meta?.name ?? path}</span>
                        <span className="run-changes__val">{fmtValue(f?.value, meta?.unit ?? '')}</span>
                        {rs && rs !== 'requested' ? <StateChip status={rs as FieldStatus} title={fd?.detail} /> : null}
                        {fd?.mechanism && <span className="run-changes__how faint">{fd.mechanism}</span>}
                      </li>
                    )
                  })}
                </ul>
              )}
              {reconciled && (
                <p className="small muted">
                  {(() => {
                    const statuses = changed.map((p) => getField(reconciled, p)?.status)
                    const n = (s: FieldStatus) => statuses.filter((x) => x === s).length
                    return `${n('reproduced')} reproduced · ${n('approximated')} approximated · ${n('unavailable')} unavailable`
                  })()}
                </p>
              )}
              <div className="run-side__actions">
                <button className="btn btn--primary" onClick={runOnce} disabled={!canRun}>
                  <Icon name="play" size={14} />
                  {phase === 'reconciling' ? 'Checking fidelity…' : phase === 'running' ? 'Running…' : 'Run once'}
                </button>
                <button className="btn" onClick={reconcile} disabled={!profile || phase === 'running' || phase === 'reconciling'}>
                  Check fidelity
                </button>
              </div>
              <div className="run-side__actions">
                <button className="btn btn--ghost btn--sm" onClick={() => onNavigate('experiment')} disabled={!profile}>
                  <Icon name="flask" size={13} /> Isolate the cause
                </button>
                <button className="btn btn--ghost btn--sm" onClick={() => onNavigate('threshold')} disabled={!profile}>
                  <Icon name="gauge" size={13} /> Find a threshold
                </button>
              </div>
            </section>
          </div>
        </aside>
      </div>

      {/* result */}
      {(phase === 'setup-error' || phase === 'error') && error && (
        <section className="section" aria-live="polite">
          <p className="note" data-tone={phase === 'setup-error' ? 'warn' : 'fail'} role="alert">
            <Icon name="alert" />
            <span>
              {phase === 'setup-error' ? (
                <>
                  <strong>Morph could not launch the command.</strong> This is a setup problem, not an application failure. {error}
                </>
              ) : (
                error
              )}
            </span>
          </p>
        </section>
      )}

      {lastRun && phase !== 'running' && <RunOutcome result={lastRun} tab={outputTab} setTab={setOutputTab} detailsOpen={detailsOpen} setDetailsOpen={setDetailsOpen} onNavigate={onNavigate} />}
    </>
  )
}

function RunOutcome({
  result,
  tab,
  setTab,
  detailsOpen,
  setDetailsOpen,
  onNavigate,
}: {
  result: RunResult
  tab: 'stdout' | 'stderr'
  setTab: (t: 'stdout' | 'stderr') => void
  detailsOpen: boolean
  setDetailsOpen: (v: boolean) => void
  onNavigate: (s: ScreenId) => void
}) {
  const outcome = structuredOutcome(result.stdout)
  const signal = outcome && typeof outcome.signal === 'string' ? outcome.signal : result.error_type
  const detail = outcome && typeof outcome.detail === 'string' ? outcome.detail : result.error_message
  const stderrTail = result.stderr.trim().split('\n').slice(-3).join('\n')
  const invalid = result.invalid

  return (
    <section className="section reveal" aria-labelledby="run-result-title">
      <div className="section__head">
        <h2 id="run-result-title">Last run</h2>
        <span className="small muted">{result.run_id}</span>
      </div>
      <div className="outcome">
        <div className="outcome__head">
          <span className="outcome__pill" data-state={invalid ? 'invalid' : result.passed ? 'pass' : 'fail'} role="status">
            <Icon name={invalid ? 'alert' : result.passed ? 'check' : 'x'} size={14} />
            {invalid ? 'Invalid' : result.passed ? 'Passed' : 'Failed'}
          </span>
          <dl className="outcome__stats">
            <div>
              <dt>Exit</dt>
              <dd>{result.exit_code}</dd>
            </div>
            <div>
              <dt>Duration</dt>
              <dd>{fmtMs(result.duration_ms)}</dd>
            </div>
            <div>
              <dt>Peak memory</dt>
              <dd>{result.peak_memory_mb != null ? `${result.peak_memory_mb.toFixed(1)} MB` : '—'}</dd>
            </div>
            {result.telemetry?.cpu_percent != null && (
              <div>
                <dt>CPU</dt>
                <dd>{result.telemetry.cpu_percent.toFixed(0)} %</dd>
              </div>
            )}
          </dl>
        </div>

        {invalid && (
          <p className="note" data-tone="warn">
            <Icon name="alert" />
            <span>This run does not count as evidence: {result.invalid_reason ?? 'the command could not be attempted.'}</span>
          </p>
        )}
        {!result.passed && !invalid && (signal || detail || stderrTail) && (
          <p className="outcome__error">
            {signal && <strong>{signal}</strong>}
            {signal && detail && ': '}
            {detail}
            {!signal && !detail && <span className="muted">{stderrTail}</span>}
          </p>
        )}

        <div className="tabs" role="tablist" aria-label="Run output">
          {(['stdout', 'stderr'] as const).map((t) => (
            <button
              key={t}
              role="tab"
              id={`tab-${t}`}
              aria-selected={tab === t}
              aria-controls={`panel-${t}`}
              tabIndex={tab === t ? 0 : -1}
              className="tabs__tab"
              onClick={() => setTab(t)}
              onKeyDown={(e) => {
                if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
                  setTab(t === 'stdout' ? 'stderr' : 'stdout')
                  ;(document.getElementById(`tab-${t === 'stdout' ? 'stderr' : 'stdout'}`) as HTMLElement | null)?.focus()
                }
              }}
            >
              {t}
              {t === 'stderr' && result.stderr.trim() && <span className="tabs__dot" aria-hidden />}
            </button>
          ))}
        </div>
        <div role="tabpanel" id={`panel-${tab}`} aria-labelledby={`tab-${tab}`}>
          <CodeBlock code={result[tab]} maxHeight={260} wrap />
        </div>

        <div className="row">
          <button className="btn btn--sm" onClick={() => onNavigate('experiment')}>
            <Icon name="flask" size={13} /> Isolate the cause
          </button>
          <button className="btn btn--sm" onClick={() => onNavigate('regressions')}>
            <Icon name="bookmark" size={13} /> Save as regression
          </button>
          <button className="btn btn--ghost btn--sm" aria-expanded={detailsOpen} onClick={() => setDetailsOpen(!detailsOpen)}>
            <Icon name={detailsOpen ? 'chevronDown' : 'chevronRight'} size={13} /> Provenance and fidelity
          </button>
        </div>

        {detailsOpen && (
          <div className="drawer">
            <dl className="kv">
              <div>
                <dt>Command</dt>
                <dd>{result.command ?? '—'}</dd>
              </div>
              <div>
                <dt>Adapter</dt>
                <dd>{result.adapter ?? '—'}</dd>
              </div>
              <div>
                <dt>Seed</dt>
                <dd>{result.seed ?? '—'}</dd>
              </div>
              <div>
                <dt>Morph</dt>
                <dd>{result.morph_version ?? '—'}</dd>
              </div>
              <div>
                <dt>Host fingerprint</dt>
                <dd>{result.host_fingerprint ?? '—'}</dd>
              </div>
              <div>
                <dt>Profile hash</dt>
                <dd>{result.profile_hash ?? '—'}</dd>
              </div>
              <div>
                <dt>When</dt>
                <dd>{result.timestamp}</dd>
              </div>
            </dl>
            {result.fidelity && Object.keys(result.fidelity).length > 0 && (
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Field</th>
                      <th>Status</th>
                      <th>Mechanism</th>
                      <th>Detail</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(result.fidelity).map(([k, f]) => (
                      <tr key={k}>
                        <td>{k}</td>
                        <td>
                          <StateChip status={f.status as FieldStatus} />
                        </td>
                        <td className="muted">{f.mechanism || '—'}</td>
                        <td className="muted">{f.detail || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {(!result.fidelity || Object.keys(result.fidelity).length === 0) && (
              <p className="small muted">
                <Chip>no fidelity report</Chip> This server did not report per-field fidelity for the run.
              </p>
            )}
          </div>
        )}
      </div>
    </section>
  )
}
