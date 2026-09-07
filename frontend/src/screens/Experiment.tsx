import { useEffect, useMemo, useState } from 'react'
import { ApiError, api, errorMessage } from '../api/client'
import { getField } from '../api/profileFields'
import type { ComparisonResult, ExperimentResult, MinimizeResult, TrialEvent } from '../api/types'
import { EvidenceTrack } from '../components/charts/EvidenceTrack'
import { Chip } from '../components/ui/Chips'
import { CodeBlock } from '../components/ui/CodeBlock'
import { Icon } from '../components/ui/Icon'
import { useJobStream } from '../hooks/useJobStream'
import { fmtE, fmtMs, fmtP, fmtRate, plural } from '../lib/format'
import { formatSummary } from '../lib/summary'
import type { ScreenId } from '../routes'
import { setState, useStore } from '../state/store'
import { useRunDraft } from '../state/useRunDraft'
import '../components/charts/charts.css'
import './screens.css'

interface Trial {
  index: number
  passed: boolean
  durationMs: number | null
  errorType: string | null
  stderrTail: string | null
  stdoutTail: string | null
}

interface Lane {
  id: string
  total: number
  trials: Trial[]
  failures: number
  done: boolean
  eValue: number | null
  threshold: number | null
  pairs: number | null
  decisive: boolean
  pValue: number | null
  history: number[]
  comparison: { p: number | null; e: number | null; significant: boolean | null; effect: string | null; stoppedEarly: boolean } | null
}

interface Derived {
  order: string[]
  lanes: Record<string, Lane>
  phase: string
  mode: string
  verdict: { classification: string; strongest: string; summary: string; interactionProbability: number | null } | null
}

function reduceEvents(events: TrialEvent[]): Derived {
  const lanes: Record<string, Lane> = {}
  const order: string[] = []
  let phase = ''
  let mode = ''
  let verdict: Derived['verdict'] = null
  const lane = (id: string) => {
    if (!lanes[id]) {
      lanes[id] = { id, total: 0, trials: [], failures: 0, done: false, eValue: null, threshold: null, pairs: null, decisive: false, pValue: null, history: [], comparison: null }
      order.push(id)
    }
    return lanes[id]
  }
  for (const ev of events) {
    switch (ev.kind) {
      case 'phase_start':
        phase = ev.phase
        if (typeof ev.extra?.mode === 'string') mode = ev.extra.mode
        break
      case 'phase_done':
        if (ev.phase === phase) phase = ''
        break
      case 'condition_start':
        if (ev.condition) lane(ev.condition).total = ev.total ?? 0
        break
      case 'trial': {
        if (!ev.condition) break
        const l = lane(ev.condition)
        l.trials.push({
          index: ev.trial_index ?? l.trials.length,
          passed: ev.passed === true,
          durationMs: ev.duration_ms ?? null,
          errorType: ev.error_type ?? null,
          stderrTail: ev.stderr_tail ?? null,
          stdoutTail: ev.stdout_tail ?? null,
        })
        if (ev.passed === false) l.failures += 1
        if (ev.total != null) l.total = ev.total
        break
      }
      case 'evidence': {
        if (!ev.condition) break
        const l = lane(ev.condition)
        l.eValue = ev.e_value ?? l.eValue
        l.threshold = ev.evidence_threshold ?? l.threshold
        l.pairs = ev.pairs ?? l.pairs
        l.decisive = ev.decisive === true || l.decisive
        l.pValue = ev.p_value ?? l.pValue
        if (ev.e_value != null) l.history.push(ev.e_value)
        break
      }
      case 'condition_done': {
        if (!ev.condition) break
        const l = lane(ev.condition)
        l.done = true
        if (ev.failures != null) l.failures = ev.failures
        if (ev.total != null) l.total = ev.total
        break
      }
      case 'comparison': {
        if (!ev.condition) break
        const l = lane(ev.condition)
        l.comparison = {
          p: ev.p_value ?? null,
          e: ev.e_value ?? null,
          significant: ev.is_significant ?? null,
          effect: ev.effect_label ?? null,
          stoppedEarly: Boolean(ev.extra?.stopped_early),
        }
        break
      }
      case 'verdict':
        verdict = {
          classification: ev.classification ?? 'unknown',
          strongest: ev.strongest_condition ?? '',
          summary: typeof ev.extra?.summary === 'string' ? ev.extra.summary : '',
          interactionProbability: typeof ev.extra?.interaction_probability === 'number' ? ev.extra.interaction_probability : null,
        }
        break
      default:
        break
    }
  }
  return { order, lanes, phase, mode, verdict }
}

const CLASS_LABEL: Record<string, { title: string; tone: 'fail' | 'warn' | 'ok' | 'gold' }> = {
  environment_caused: { title: 'Environment caused', tone: 'fail' },
  environment_exposed: { title: 'Environment exposed', tone: 'warn' },
  application_internal: { title: 'Application internal', tone: 'gold' },
  no_effect: { title: 'No effect', tone: 'ok' },
  unknown: { title: 'Inconclusive', tone: 'warn' },
}

export function Experiment({ onNavigate }: { onNavigate: (s: ScreenId) => void }) {
  const { draft, set } = useRunDraft()
  const lastId = useStore((s) => s.lastExperimentId)
  const stored = useStore((s) => s.lastExperiment)
  const [jobId, setJobId] = useState<string | null>(lastId)
  const [starting, setStarting] = useState(false)
  const [startError, setStartError] = useState<{ message: string; setup: boolean } | null>(null)
  const [selected, setSelected] = useState<{ lane: string; index: number } | null>(null)
  const [minimize, setMinimize] = useState<{ state: 'idle' | 'running' | 'done' | 'error' | 'missing'; result?: MinimizeResult; message?: string }>({ state: 'idle' })
  const stream = useJobStream<ExperimentResult>('experiment', jobId)

  const derived = useMemo(() => reduceEvents(stream.events), [stream.events])
  const result = stream.result ?? (stream.status === 'error' && stream.error?.message.includes('no longer knows') ? stored : null)

  useEffect(() => {
    if (stream.result && jobId) setState({ lastExperiment: stream.result, lastExperimentId: jobId })
  }, [stream.result, jobId])

  const profile = draft.profile
  const latency = Number(profile && getField(profile, 'network.latency_ms')?.value) || 0
  const loss = Number(profile && getField(profile, 'network.packet_loss_percent')?.value) || 0
  const targetSummary = profile ? formatSummary(profile, draft.hostProfile) : ''

  const laneLabel = (id: string) => {
    switch (id) {
      case 'baseline':
        return 'Baseline: this machine as it is'
      case 'latency_only':
        return `Latency only · ${latency} ms`
      case 'loss_only':
        return `Packet loss only · ${loss} %`
      case 'full_treatment':
        return latency && loss ? `Latency + loss · ${latency} ms, ${loss} %` : `Target environment${targetSummary ? ` · ${targetSummary}` : ''}`
      case 'treatment':
        return `Target environment${targetSummary ? ` · ${targetSummary}` : ''}`
      default:
        return id.replace(/_/g, ' ')
    }
  }

  async function start() {
    if (!profile || !draft.command.trim()) return
    setStarting(true)
    setStartError(null)
    setSelected(null)
    setMinimize({ state: 'idle' })
    try {
      const { experiment_id } = await api.startExperimentStream({
        command: draft.command.trim(),
        cwd: draft.cwd,
        target_profile: profile,
        mode: draft.mode,
        max_rounds: draft.maxRounds,
        trials: draft.trials,
        alpha: draft.alpha,
        timeout_sec: draft.timeoutSec,
      })
      setState({ lastExperimentId: experiment_id, lastExperiment: null })
      setJobId(experiment_id)
    } catch (err) {
      setStartError({ message: errorMessage(err), setup: err instanceof ApiError && err.isSetupError })
    } finally {
      setStarting(false)
    }
  }

  async function cancel() {
    if (!jobId) return
    try {
      await api.cancelExperiment(jobId)
    } catch (err) {
      setStartError({ message: errorMessage(err), setup: false })
    }
  }

  async function runMinimize() {
    if (!profile) return
    setMinimize({ state: 'running' })
    try {
      const r = await api.minimize({ command: draft.command.trim(), cwd: draft.cwd, target_profile: profile, timeout: draft.timeoutSec })
      setMinimize({ state: 'done', result: r })
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) setMinimize({ state: 'missing' })
      else setMinimize({ state: 'error', message: errorMessage(err) })
    }
  }

  const running = stream.status === 'live' || stream.status === 'connecting' || starting
  const noNetworkRequest = profile != null && latency === 0 && loss === 0
  const canStart = Boolean(profile && draft.command.trim()) && !running

  // Which trial's evidence to show: the selection, else the latest failure of
  // the strongest condition, else the latest failure anywhere.
  const evidence = useMemo(() => {
    const pick = (laneId: string, idx: number) => {
      const t = derived.lanes[laneId]?.trials.find((x) => x.index === idx)
      return t ? { laneId, trial: t } : null
    }
    if (selected) return pick(selected.lane, selected.index)
    const strongest = derived.verdict?.strongest || result?.strongest_condition
    const candidates = strongest && derived.lanes[strongest] ? [strongest] : derived.order
    for (const id of [...candidates].reverse()) {
      const fails = derived.lanes[id]?.trials.filter((t) => !t.passed) ?? []
      if (fails.length) return { laneId: id, trial: fails[fails.length - 1] }
    }
    return null
  }, [selected, derived, result])

  const classification = result?.classification ?? derived.verdict?.classification ?? null
  const verdictMeta = classification ? (CLASS_LABEL[classification] ?? CLASS_LABEL.unknown) : null
  const comparisons = result?.comparisons ?? []
  const baselineRate = result?.baseline ? result.baseline.failures / Math.max(1, result.baseline.total_runs) : rateOf(derived.lanes.baseline)

  return (
    <>
      <header className="page__head">
        <div>
          <h1>Experiment</h1>
          <p>
            Baseline and treatment run in matched pairs. The evidence you see live is anytime-valid: stopping when it crosses the line does not inflate the false-positive rate.
          </p>
        </div>
      </header>

      {/* run configuration */}
      <section className="exp-config">
        <div className="exp-config__what">
          <div>
            <span className="small muted">Command</span>
            <div>
              {draft.command ? <code className="inline-code">{draft.command}</code> : <button className="link-btn" onClick={() => onNavigate('projects')}>Connect a project</button>}
            </div>
          </div>
          <div>
            <span className="small muted">Target</span>
            <div>
              {targetSummary || <span className="muted">same as this machine</span>}{' '}
              <button className="link-btn small" onClick={() => onNavigate('run')}>
                edit
              </button>
            </div>
          </div>
        </div>
        <div className="exp-config__knobs">
          <div className="field">
            <span className="field__label" id="mode-label">
              Mode
            </span>
            <div className="segmented" role="group" aria-labelledby="mode-label">
              <button aria-pressed={draft.mode === 'sequential'} onClick={() => set({ mode: 'sequential' })} disabled={running}>
                Sequential
              </button>
              <button aria-pressed={draft.mode === 'batch'} onClick={() => set({ mode: 'batch' })} disabled={running}>
                Batch
              </button>
            </div>
          </div>
          {draft.mode === 'sequential' ? (
            <div className="field">
              <label htmlFor="max-rounds">Max rounds</label>
              <input id="max-rounds" className="input input--number" type="number" min={1} max={200} value={draft.maxRounds} disabled={running} onChange={(e) => set({ maxRounds: Math.max(1, Number(e.target.value) || 1) })} />
            </div>
          ) : (
            <div className="field">
              <label htmlFor="trials">Trials per condition</label>
              <input id="trials" className="input input--number" type="number" min={1} max={500} value={draft.trials} disabled={running} onChange={(e) => set({ trials: Math.max(1, Number(e.target.value) || 1) })} />
            </div>
          )}
          <div className="field">
            <label htmlFor="alpha">α</label>
            <input id="alpha" className="input input--number" type="number" min={0.001} max={0.5} step={0.01} value={draft.alpha} disabled={running} onChange={(e) => set({ alpha: Math.min(0.5, Math.max(0.001, Number(e.target.value) || 0.05)) })} />
          </div>
          <div className="exp-config__go">
            {running ? (
              <button className="btn btn--danger" onClick={cancel}>
                <Icon name="stop" size={14} /> Cancel
              </button>
            ) : (
              <button className="btn btn--primary" onClick={start} disabled={!canStart}>
                <Icon name="play" size={14} /> {result || stream.events.length ? 'Run again' : 'Start'}
              </button>
            )}
          </div>
        </div>
        {noNetworkRequest && !running && (
          <p className="small muted">
            The target requests no latency or packet loss, so there is only one condition to compare. Pick the Flagship preset on the Run screen to isolate latency, loss and their interaction.
          </p>
        )}
      </section>

      {startError && (
        <p className="note" data-tone={startError.setup ? 'warn' : 'fail'} role="alert">
          <Icon name="alert" />
          <span>
            {startError.setup && <strong>Morph could not launch the command. </strong>}
            {startError.message}
          </span>
        </p>
      )}
      {stream.status === 'disconnected' && (
        <p className="note" data-tone="warn" role="alert">
          <Icon name="alert" />
          <span>Lost the connection to the experiment stream.</span>
          <button className="btn btn--sm" onClick={stream.reconnect}>
            Reconnect
          </button>
        </p>
      )}
      {stream.status === 'error' && stream.error && !result && (
        <p className="note" data-tone={stream.error.cancelled ? 'warn' : 'fail'} role="alert">
          <Icon name="alert" />
          <span>
            {stream.error.cancelled ? 'Cancelled.' : stream.error.setupError ? <><strong>Morph could not launch the command. </strong>{stream.error.message}</> : stream.error.message}
          </span>
        </p>
      )}

      {/* status line */}
      <p className="exp-status small muted" role="status" aria-live="polite">
        {stream.status === 'connecting' && 'Connecting to the experiment…'}
        {stream.status === 'live' && (derived.phase ? `Running · ${derived.phase}${derived.mode ? ` · ${derived.mode}` : ''}` : 'Running…')}
        {stream.status === 'done' && 'Finished.'}
        {stream.attempts > 0 && stream.status !== 'live' && stream.status !== 'done' && ` Reconnecting (${stream.attempts})…`}
      </p>

      {/* verdict, conclusion first */}
      {verdictMeta && (
        <section className="verdict reveal" data-tone={verdictMeta.tone} aria-labelledby="verdict-title">
          <div className="verdict__main">
            <h2 id="verdict-title" className="verdict__title">
              {verdictMeta.title}
            </h2>
            <p className="verdict__summary">{result?.summary || derived.verdict?.summary}</p>
            {(result?.strongest_condition || derived.verdict?.strongest) && (
              <p className="small muted">Strongest condition: {laneLabel(result?.strongest_condition || derived.verdict!.strongest)}</p>
            )}
            {derived.verdict?.interactionProbability != null && (
              <p className="small muted">Interaction probability: {fmtRate(derived.verdict.interactionProbability)}</p>
            )}
            {result?.warnings && result.warnings.length > 0 && (
              <ul className="verdict__warnings">
                {result.warnings.map((w) => (
                  <li key={w}>
                    <Icon name="alert" size={13} /> {w}
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div className="verdict__actions">
            <button className="btn" onClick={() => onNavigate('regressions')}>
              <Icon name="bookmark" size={14} /> Save as regression
            </button>
            <button className="btn" onClick={() => onNavigate('threshold')}>
              <Icon name="gauge" size={14} /> Find the threshold
            </button>
            {(classification === 'environment_caused' || classification === 'environment_exposed') && (
              <button className="btn" onClick={runMinimize} disabled={minimize.state === 'running' || minimize.state === 'missing'}>
                <Icon name="minus" size={14} /> {minimize.state === 'running' ? 'Minimizing…' : 'Minimal failing set'}
              </button>
            )}
          </div>
          {minimize.state === 'missing' && <p className="small muted">This server does not offer POST /minimize.</p>}
          {minimize.state === 'error' && <p className="field__error">{minimize.message}</p>}
          {minimize.state === 'done' && minimize.result && (
            <div className="row">
              <span className="small muted">Minimal failing set:</span>
              {minimize.result.minimal.length === 0 && <span className="small muted">none reproduced the failure</span>}
              {minimize.result.minimal.map((c) => (
                <Chip key={c} tone="fail" icon="x">
                  {laneLabel(c)}
                </Chip>
              ))}
              <span className="small muted">{minimize.result.summary}</span>
            </div>
          )}
        </section>
      )}

      {/* lanes */}
      {derived.order.length > 0 && (
        <section className="section" aria-label="Conditions">
          <div className="lanes">
            {derived.order.map((id) => {
              const l = derived.lanes[id]
              const isBaseline = id === 'baseline'
              const ran = l.trials.length
              return (
                <article className="lane" key={id} data-decisive={l.decisive} data-strongest={(result?.strongest_condition || derived.verdict?.strongest) === id}>
                  <header className="lane__head">
                    <h3 className="lane__name">{laneLabel(id)}</h3>
                    <span className="lane__count small muted">
                      {l.failures} failed · {ran}/{l.total || '?'} run
                      {l.decisive && (
                        <>
                          {' '}
                          <span className="stamp">Decisive</span>
                          {l.comparison?.stoppedEarly || (l.done && ran < l.total) ? ` · stopped early after ${plural(l.pairs ?? ran, 'pair')}` : ''}
                        </>
                      )}
                    </span>
                  </header>
                  <ul className="ticks" aria-label={`${laneLabel(id)} trials`}>
                    {l.trials.map((t) => (
                      <li key={t.index}>
                        <button
                          className="tick"
                          data-passed={t.passed}
                          data-selected={selected?.lane === id && selected.index === t.index}
                          aria-label={`Trial ${t.index + 1}: ${t.passed ? 'passed' : 'failed'}${t.errorType ? `, ${t.errorType}` : ''}`}
                          aria-pressed={selected?.lane === id && selected.index === t.index}
                          onClick={() => setSelected({ lane: id, index: t.index })}
                          title={`${t.passed ? 'passed' : 'failed'} · ${fmtMs(t.durationMs)}`}
                        />
                      </li>
                    ))}
                    {Array.from({ length: Math.max(0, l.total - ran) }).map((_, i) => (
                      <li key={`p${i}`}>
                        <span className="tick" data-pending aria-hidden />
                      </li>
                    ))}
                  </ul>
                  {!isBaseline && (l.eValue != null || l.threshold != null) && (
                    <div className="lane__evidence">
                      <EvidenceTrack
                        eValue={l.eValue}
                        threshold={l.threshold}
                        decisive={l.decisive}
                        history={l.history}
                        label={`Evidence for ${laneLabel(id)}: e-value ${fmtE(l.eValue)} of ${fmtE(l.threshold)} needed`}
                      />
                      <div className="lane__stats small">
                        <span>
                          <span className="muted">E</span> {fmtE(l.eValue)}
                        </span>
                        <span>
                          <span className="muted">p</span> {fmtP(l.pValue)}
                        </span>
                        <span>
                          <span className="muted">rate</span> {fmtRate(rateOf(l))}
                        </span>
                        {l.pairs != null && (
                          <span>
                            <span className="muted">pairs</span> {l.pairs}
                          </span>
                        )}
                      </div>
                    </div>
                  )}
                  {!isBaseline && l.eValue == null && l.comparison && (
                    <div className="lane__stats small">
                      <span>
                        <span className="muted">p</span> {fmtP(l.comparison.p)}
                      </span>
                      <span>
                        <span className="muted">rate</span> {fmtRate(rateOf(l))}
                      </span>
                      {l.comparison.significant != null && <span>{l.comparison.significant ? 'significant' : 'not significant'}</span>}
                    </div>
                  )}
                  {isBaseline && ran > 0 && (
                    <div className="lane__stats small">
                      <span>
                        <span className="muted">rate</span> {fmtRate(rateOf(l))}
                      </span>
                    </div>
                  )}
                </article>
              )
            })}
          </div>
        </section>
      )}

      {/* interaction matrix + evidence pane */}
      {(derived.lanes.latency_only && derived.lanes.loss_only && derived.lanes.full_treatment) || evidence ? (
        <section className="section exp-detail">
          {derived.lanes.latency_only && derived.lanes.loss_only && derived.lanes.full_treatment && (
            <div>
              <h2 className="exp-detail__title">Interaction</h2>
              <p className="small muted" style={{ marginBottom: 'var(--s-3)' }}>
                Failure rate by condition. If neither single condition moves the rate but the pair does, the fault is an interaction.
              </p>
              <InteractionMatrix
                baseline={baselineRate}
                latency={rateOf(derived.lanes.latency_only)}
                loss={rateOf(derived.lanes.loss_only)}
                both={rateOf(derived.lanes.full_treatment)}
                latencyLabel={`${latency} ms`}
                lossLabel={`${loss} %`}
              />
            </div>
          )}
          {evidence && (
            <div className="evidence-pane">
              <h2 className="exp-detail__title">Evidence</h2>
              <p className="small muted">
                {laneLabel(evidence.laneId)} · trial {evidence.trial.index + 1} · {evidence.trial.passed ? 'passed' : 'failed'} · {fmtMs(evidence.trial.durationMs)}
              </p>
              {evidence.trial.errorType && <p className="evidence-pane__type">{evidence.trial.errorType}</p>}
              <CodeBlock code={(evidence.trial.stderrTail?.trim() || evidence.trial.stdoutTail?.trim() || '(no output captured)').trim()} filename={evidence.trial.stderrTail?.trim() ? 'stderr (tail)' : 'stdout (tail)'} maxHeight={180} wrap />
            </div>
          )}
        </section>
      ) : null}

      {/* comparison table */}
      {comparisons.length > 0 && (
        <section className="section">
          <div className="section__head">
            <h2>Comparisons</h2>
            <span className="small muted">{comparisons[0].method === 'paired_e_value' ? 'paired e-value, anytime-valid' : comparisons[0].method === 'fisher_holm' ? 'Fisher exact, Holm-adjusted' : 'Fisher exact'}</span>
          </div>
          <ComparisonTable rows={[...comparisons, ...(result?.interactions ?? [])]} label={laneLabel} />
        </section>
      )}

      {!jobId && !result && stream.events.length === 0 && (
        <div className="empty">
          <h2>No experiment yet</h2>
          <p>Pick a project and a target environment, then start. The flagship demo is apps/pool_retry at 120 ms latency and 18 % loss.</p>
        </div>
      )}
    </>
  )
}

function rateOf(l: Lane | undefined): number | null {
  if (!l || l.trials.length === 0) return null
  return l.failures / l.trials.length
}

function level(r: number | null): 'low' | 'mid' | 'high' {
  if (r == null) return 'low'
  return r >= 0.5 ? 'high' : r > 0.1 ? 'mid' : 'low'
}

function InteractionMatrix({ baseline, latency, loss, both, latencyLabel, lossLabel }: { baseline: number | null; latency: number | null; loss: number | null; both: number | null; latencyLabel: string; lossLabel: string }) {
  const cell = (r: number | null, name: string) => (
    <div className="matrix__cell" data-level={level(r)} role="cell">
      <strong>{fmtRate(r)}</strong>
      <span className="small muted">{name}</span>
    </div>
  )
  return (
    <div className="matrix" role="table" aria-label="Failure rate by latency and packet loss">
      <div className="matrix__corner" role="cell" />
      <div className="matrix__head" role="columnheader">
        no loss
      </div>
      <div className="matrix__head" role="columnheader">
        loss {lossLabel}
      </div>
      <div className="matrix__head" role="rowheader">
        no latency
      </div>
      {cell(baseline, 'baseline')}
      {cell(loss, 'loss only')}
      <div className="matrix__head" role="rowheader">
        latency {latencyLabel}
      </div>
      {cell(latency, 'latency only')}
      {cell(both, 'both')}
    </div>
  )
}

function ComparisonTable({ rows, label }: { rows: ComparisonResult[]; label: (id: string) => string }) {
  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            <th>Condition</th>
            <th className="num">Trials</th>
            <th className="num">Failures</th>
            <th className="num">Rate</th>
            <th className="num">Δ vs baseline</th>
            <th className="num">Evidence</th>
            <th>Verdict</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((c) => {
            const rate = c.treatment_total ? c.treatment_failures / c.treatment_total : 0
            const seq = c.method === 'paired_e_value'
            return (
              <tr key={c.condition_label} data-significant={c.is_significant}>
                <td>{label(c.condition_label)}</td>
                <td className="num">{c.treatment_total}</td>
                <td className="num">{c.treatment_failures}</td>
                <td className="num">{fmtRate(rate)}</td>
                <td className="num">
                  {c.risk_difference != null ? (
                    <>
                      {c.risk_difference >= 0 ? '+' : ''}
                      {fmtRate(c.risk_difference)}
                      {c.risk_difference_ci && <span className="faint"> [{fmtRate(c.risk_difference_ci[0])}, {fmtRate(c.risk_difference_ci[1])}]</span>}
                    </>
                  ) : (
                    '—'
                  )}
                </td>
                <td className="num">
                  {seq ? (
                    <>
                      E {fmtE(c.e_value)} · p {fmtP(c.p_value)}
                    </>
                  ) : (
                    <>
                      p {fmtP(c.p_value)}
                      {c.p_value_adjusted != null && c.method === 'fisher_holm' && <span className="faint"> adj {fmtP(c.p_value_adjusted)}</span>}
                    </>
                  )}
                </td>
                <td>
                  {c.is_significant ? (
                    <Chip tone="fail" icon="x">
                      {seq ? 'decisive' : 'significant'}
                    </Chip>
                  ) : c.effect_label === 'significant_decrease' ? (
                    <Chip tone="ok" icon="check">
                      fails less
                    </Chip>
                  ) : (
                    <Chip>not decisive</Chip>
                  )}
                  {seq && c.stopped_early && <span className="small muted"> · stopped after {plural(c.pairs ?? 0, 'pair')}</span>}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
