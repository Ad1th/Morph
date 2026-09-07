import { useEffect, useMemo, useState } from 'react'
import { ApiError, api, errorMessage } from '../api/client'
import type { ParameterMetadata, ThresholdResult } from '../api/types'
import { DoseResponseChart } from '../components/charts/DoseResponseChart'
import { Chip } from '../components/ui/Chips'
import { Icon } from '../components/ui/Icon'
import { useJobStream } from '../hooks/useJobStream'
import { fmtNumber, fmtRate, plural } from '../lib/format'
import type { ScreenId } from '../routes'
import { setState, useStore } from '../state/store'
import { resolveMax, useRunDraft } from '../state/useRunDraft'
import '../components/charts/charts.css'
import './screens.css'

// Sensible search ranges per parameter: the catalog max for latency is 5000 ms
// but the interesting band is far lower, so seed the defaults tighter.
const RANGE_HINT: Record<string, [number, number]> = {
  'network.latency_ms': [0, 500],
  'network.packet_loss_percent': [0, 30],
  'network.jitter_ms': [0, 200],
  'network.bandwidth_mbps': [0.1, 100],
}

export function Threshold({ onNavigate }: { onNavigate: (s: ScreenId) => void }) {
  const { draft } = useRunDraft()
  const stored = useStore((s) => s.lastThreshold)
  const storedParam = useStore((s) => s.lastThresholdParam)
  const [catalog, setCatalog] = useState<Record<string, ParameterMetadata> | null>(null)
  const [parameter, setParameter] = useState(storedParam ?? 'network.latency_ms')
  const [low, setLow] = useState('0')
  const [high, setHigh] = useState('500')
  const [method, setMethod] = useState<'bayes' | 'bisect'>('bayes')
  const [maxTrials, setMaxTrials] = useState(30)
  const [trialsPerProbe, setTrialsPerProbe] = useState(3)
  const [jobId, setJobId] = useState<string | null>(null)
  const [blocking, setBlocking] = useState<{ state: 'idle' | 'running' | 'done' }>({ state: 'idle' })
  const [blockingResult, setBlockingResult] = useState<ThresholdResult | null>(null)
  const [error, setError] = useState<{ message: string; setup: boolean } | null>(null)
  const [starting, setStarting] = useState(false)
  const stream = useJobStream<ThresholdResult>('threshold', jobId)

  useEffect(() => {
    api.getParameterCatalog().then(setCatalog).catch((err) => setError({ message: errorMessage(err), setup: false }))
  }, [])

  const numeric = useMemo(() => (catalog ? Object.values(catalog).filter((m) => m.experimentable && m.min != null) : []), [catalog])
  const meta = numeric.find((m) => m.field_path === parameter) ?? null

  // Seed low/high whenever the parameter changes.
  useEffect(() => {
    if (!meta) return
    const hint = RANGE_HINT[meta.field_path]
    const hi = hint ? hint[1] : resolveMax(meta, draft.hostProfile, draft.profile)
    const lo = hint ? hint[0] : (meta.min ?? 0)
    setLow(String(lo))
    setHigh(String(hi))
  }, [meta, draft.hostProfile, draft.profile])

  const result = stream.result ?? blockingResult ?? (jobId == null && blocking.state === 'idle' ? stored : null)
  const running = starting || stream.status === 'live' || stream.status === 'connecting' || blocking.state === 'running'

  useEffect(() => {
    if (stream.result) setState({ lastThreshold: stream.result, lastThresholdParam: parameter, lastThresholdId: jobId })
    // parameter is the one the job was started with; jobId identifies it
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stream.result])

  const probes = useMemo(() => {
    const live = stream.events.filter((e) => e.kind === 'search_probe' && e.param_value != null).map((e) => ({ value: e.param_value as number, passed: Boolean(e.extra?.passed ?? (e.failure_rate ?? 0) < 0.5) }))
    if (live.length) return live
    return (result?.search_points ?? []).filter((p) => p.value != null).map((p) => ({ value: p.value as number, passed: p.passed ?? (p.failure_rate ?? 0) <= 0.5 }))
  }, [stream.events, result])

  const lastProbe = [...stream.events].reverse().find((e) => e.kind === 'search_probe')

  const lo = Number(low)
  const hi = Number(high)
  const valid = Number.isFinite(lo) && Number.isFinite(hi) && hi > lo
  const canStart = Boolean(draft.command.trim() && meta && valid) && !running

  async function start() {
    if (!meta || !draft.profile) return
    setStarting(true)
    setError(null)
    setBlockingResult(null)
    const req = {
      command: draft.command.trim(),
      cwd: draft.cwd,
      parameter: meta.field_path,
      low: lo,
      high: hi,
      method,
      max_trials: maxTrials,
      trials: trialsPerProbe,
      profile: draft.profile,
      target: draft.target,
      timeout: draft.timeoutSec,
    }
    try {
      const { threshold_id } = await api.startThresholdStream(req)
      setJobId(threshold_id)
      setStarting(false)
    } catch (err) {
      if (err instanceof ApiError && (err.status === 404 || err.status === 405)) {
        // Older server: blocking search, no live probes.
        setStarting(false)
        setJobId(null)
        setBlocking({ state: 'running' })
        try {
          const r = await api.findThreshold(req)
          setBlockingResult(r)
          setState({ lastThreshold: r, lastThresholdParam: meta.field_path, lastThresholdId: null })
        } catch (inner) {
          setError({ message: errorMessage(inner), setup: inner instanceof ApiError && inner.isSetupError })
        } finally {
          setBlocking({ state: 'done' })
        }
      } else {
        setStarting(false)
        setError({ message: errorMessage(err), setup: err instanceof ApiError && err.isSetupError })
      }
    }
  }

  async function cancel() {
    if (!jobId) return
    try {
      await api.cancelThreshold(jobId)
    } catch (err) {
      setError({ message: errorMessage(err), setup: false })
    }
  }

  const unit = meta?.unit ?? ''
  const name = meta?.name ?? parameter
  const chartLow = result && jobId == null ? Math.min(lo, ...probes.map((p) => p.value)) : lo
  const chartHigh = result && jobId == null ? Math.max(hi, ...probes.map((p) => p.value)) : hi

  return (
    <>
      <header className="page__head">
        <div>
          <h1>Threshold</h1>
          <p>Where along one parameter do failures begin? Bayesian bisection keeps a posterior over the boundary and probes at its median, so noise is modelled instead of voted away.</p>
        </div>
      </header>

      <section className="thr-config">
        <div className="field">
          <label htmlFor="thr-param">Parameter</label>
          <select id="thr-param" className="select" value={parameter} onChange={(e) => setParameter(e.target.value)} disabled={running || !catalog}>
            {numeric.map((m) => (
              <option key={m.field_path} value={m.field_path}>
                {m.name}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="thr-low">Low ({unit})</label>
          <input id="thr-low" className="input input--number" type="number" value={low} onChange={(e) => setLow(e.target.value)} disabled={running} aria-invalid={!valid} />
        </div>
        <div className="field">
          <label htmlFor="thr-high">High ({unit})</label>
          <input id="thr-high" className="input input--number" type="number" value={high} onChange={(e) => setHigh(e.target.value)} disabled={running} aria-invalid={!valid} />
        </div>
        <div className="field">
          <span className="field__label" id="thr-method">
            Method
          </span>
          <div className="segmented" role="group" aria-labelledby="thr-method">
            <button aria-pressed={method === 'bayes'} onClick={() => setMethod('bayes')} disabled={running}>
              Bayesian
            </button>
            <button aria-pressed={method === 'bisect'} onClick={() => setMethod('bisect')} disabled={running}>
              Bisection
            </button>
          </div>
        </div>
        {method === 'bayes' ? (
          <div className="field">
            <label htmlFor="thr-max">Trial budget</label>
            <input id="thr-max" className="input input--number" type="number" min={4} max={200} value={maxTrials} onChange={(e) => setMaxTrials(Math.max(4, Number(e.target.value) || 30))} disabled={running} />
          </div>
        ) : (
          <div className="field">
            <label htmlFor="thr-tpp">Trials per probe</label>
            <input id="thr-tpp" className="input input--number" type="number" min={1} max={20} value={trialsPerProbe} onChange={(e) => setTrialsPerProbe(Math.max(1, Number(e.target.value) || 3))} disabled={running} />
          </div>
        )}
        <div className="thr-config__go">
          {running && jobId ? (
            <button className="btn btn--danger" onClick={cancel}>
              <Icon name="stop" size={14} /> Cancel
            </button>
          ) : (
            <button className="btn btn--primary" onClick={start} disabled={!canStart} title={!draft.command.trim() ? 'Connect a project first' : !valid ? 'High must be greater than low' : undefined}>
              <Icon name="play" size={14} /> {running ? 'Searching…' : 'Search'}
            </button>
          )}
        </div>
      </section>
      <p className="small muted thr-command">
        {draft.command ? (
          <>
            Runs <code className="inline-code">{draft.command}</code> with the Run screen’s profile as the base.
          </>
        ) : (
          <button className="link-btn" onClick={() => onNavigate('projects')}>
            Connect a project to search.
          </button>
        )}
      </p>

      {error && (
        <p className="note" data-tone={error.setup ? 'warn' : 'fail'} role="alert">
          <Icon name="alert" />
          <span>
            {error.setup && <strong>Morph could not launch the command. </strong>}
            {error.message}
          </span>
        </p>
      )}
      {stream.status === 'disconnected' && (
        <p className="note" data-tone="warn" role="alert">
          <Icon name="alert" />
          <span>Lost the connection to the search.</span>
          <button className="btn btn--sm" onClick={stream.reconnect}>
            Reconnect
          </button>
        </p>
      )}
      {stream.status === 'error' && stream.error && (
        <p className="note" data-tone={stream.error.cancelled ? 'warn' : 'fail'} role="alert">
          <Icon name="alert" />
          <span>{stream.error.cancelled ? 'Cancelled.' : stream.error.message}</span>
        </p>
      )}

      <p className="small muted" role="status" aria-live="polite">
        {blocking.state === 'running' && 'Searching (this server does not stream probes; results arrive when the search ends)…'}
        {stream.status === 'live' && lastProbe && `Probe ${probes.length}: ${fmtNumber(lastProbe.param_value ?? 0)} ${unit} ${lastProbe.extra?.passed ? 'passed' : 'failed'} · credible interval ${fmtNumber(lastProbe.safe_value ?? 0)}–${fmtNumber(lastProbe.failure_value ?? 0)} ${unit}`}
        {stream.status === 'connecting' && 'Connecting…'}
      </p>

      {(probes.length > 0 || result) && (
        <section className="section reveal">
          {result && <Outcome result={result} name={name} unit={unit} />}
          <DoseResponseChart
            low={chartLow}
            high={chartHigh}
            unit={unit}
            probes={probes}
            result={result}
            liveLow={lastProbe?.safe_value}
            liveHigh={lastProbe?.failure_value}
            liveMedian={lastProbe?.boundary_estimate}
            paramName={name}
          />
        </section>
      )}

      {probes.length > 0 && (
        <section className="section">
          <div className="section__head">
            <h2>Probe log</h2>
            <span className="small muted">{plural(probes.length, 'probe')}</span>
          </div>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th className="num">#</th>
                  <th className="num">{name} ({unit})</th>
                  <th>Outcome</th>
                  <th className="num">P(boundary in range)</th>
                  <th className="num">Credible interval</th>
                </tr>
              </thead>
              <tbody>
                {stream.events.filter((e) => e.kind === 'search_probe').length > 0
                  ? stream.events
                      .filter((e) => e.kind === 'search_probe')
                      .map((e, i) => (
                        <tr key={i}>
                          <td className="num">{i + 1}</td>
                          <td className="num">{fmtNumber(e.param_value ?? 0)}</td>
                          <td>
                            {e.extra?.passed ? (
                              <Chip tone="ok" icon="check">
                                passed
                              </Chip>
                            ) : (
                              <Chip tone="fail" icon="x">
                                failed
                              </Chip>
                            )}
                          </td>
                          <td className="num">{typeof e.extra?.boundary_in_range === 'number' ? fmtRate(e.extra.boundary_in_range) : '—'}</td>
                          <td className="num">
                            {e.safe_value != null && e.failure_value != null ? `${fmtNumber(e.safe_value)}–${fmtNumber(e.failure_value)}` : '—'}
                          </td>
                        </tr>
                      ))
                  : probes.map((p, i) => (
                      <tr key={i}>
                        <td className="num">{i + 1}</td>
                        <td className="num">{fmtNumber(p.value)}</td>
                        <td>
                          {p.passed ? (
                            <Chip tone="ok" icon="check">
                              passed
                            </Chip>
                          ) : (
                            <Chip tone="fail" icon="x">
                              failed
                            </Chip>
                          )}
                        </td>
                        <td className="num">—</td>
                        <td className="num">—</td>
                      </tr>
                    ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {!running && probes.length === 0 && !result && (
        <div className="empty">
          <h2>No search yet</h2>
          <p>Choose a parameter and a range that spans from “surely fine” to “surely broken”, then search.</p>
        </div>
      )}
    </>
  )
}

/** "Network latency" reads as "network latency" mid-sentence; "CPU quota" keeps its acronym. */
function lower(name: string): string {
  return /^[A-Z]{2,}/.test(name) ? name : name.charAt(0).toLowerCase() + name.slice(1)
}

function Outcome({ result, name: rawName, unit }: { result: ThresholdResult; name: string; unit: string }) {
  const name = lower(rawName)
  const outcome = result.outcome ?? (result.boundary_estimate != null ? 'boundary_found' : 'inconclusive')
  const mass = result.credible_mass != null ? `${Math.round(result.credible_mass * 100)} %` : null
  let title: string
  let tone: 'fail' | 'ok' | 'warn'
  let body: React.ReactNode
  switch (outcome) {
    case 'boundary_found':
      title = `Fails when ${name} is above about ${fmtNumber(result.boundary_estimate ?? 0)} ${unit}`
      tone = 'fail'
      body = (
        <>
          {result.credible_low != null && result.credible_high != null
            ? `${mass ?? ''} credible interval ${fmtNumber(result.credible_low)}–${fmtNumber(result.credible_high)} ${unit}.`
            : result.safe_value != null && result.failure_value != null
              ? `Safe at ${fmtNumber(result.safe_value)} ${unit}, failing at ${fmtNumber(result.failure_value)} ${unit}.`
              : null}
          {result.floor_failure_rate != null && result.ceiling_failure_rate != null && ` Below the boundary the app fails about ${fmtRate(result.floor_failure_rate)} of the time, above it about ${fmtRate(result.ceiling_failure_rate)}.`}
        </>
      )
      break
    case 'never_fails':
      title = `No boundary in range: ${name} never made it fail`
      tone = 'ok'
      body = `Every probe between the low and high value passed${result.probability_never_fails != null ? ` (P = ${fmtRate(result.probability_never_fails)})` : ''}. Widen the range upward to keep looking.`
      break
    case 'always_fails':
      title = `No boundary in range: it fails everywhere`
      tone = 'fail'
      body = `Even the lowest value failed${result.probability_always_fails != null ? ` (P = ${fmtRate(result.probability_always_fails)})` : ''}. Lower the low end, or check the baseline on the Run screen.`
      break
    default:
      title = 'Inconclusive'
      tone = 'warn'
      body = `The trials did not favour any hypothesis${result.probability_boundary_in_range != null ? ` (P boundary in range = ${fmtRate(result.probability_boundary_in_range)})` : ''}. A larger trial budget or a narrower range may settle it.`
  }
  return (
    <div className="thr-outcome" data-tone={tone}>
      <h2 className="thr-outcome__title">{title}</h2>
      <p className="muted">{body}</p>
      <p className="small faint">
        {result.method === 'probabilistic_bisection' ? 'Probabilistic bisection' : 'Bisection'}
        {result.trials != null && ` · ${plural(result.trials, 'trial')}`}
      </p>
    </div>
  )
}
