import { useCallback, useEffect, useState } from 'react'
import { api, errorMessage } from '../api/client'
import { getField } from '../api/profileFields'
import type { ExportInvariantResponse, RegressionArtifact, ReplayResult } from '../api/types'
import { Chip } from '../components/ui/Chips'
import { CodeBlock } from '../components/ui/CodeBlock'
import { Dialog } from '../components/ui/Dialog'
import { Icon } from '../components/ui/Icon'
import { fmtDate, fmtNumber, fmtRate } from '../lib/format'
import { formatSummary } from '../lib/summary'
import type { ScreenId } from '../routes'
import { useStore } from '../state/store'
import { useRunDraft } from '../state/useRunDraft'
import './screens.css'

function slug(s: string): string {
  return s
    .toLowerCase()
    .replace(/[^a-z0-9._-]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 48)
}

export function Regressions({ onNavigate }: { onNavigate: (s: ScreenId) => void }) {
  const { draft } = useRunDraft()
  const lastExperiment = useStore((s) => s.lastExperiment)
  const lastRun = useStore((s) => s.lastRun)
  const lastThreshold = useStore((s) => s.lastThreshold)
  const lastThresholdParam = useStore((s) => s.lastThresholdParam)
  const [list, setList] = useState<RegressionArtifact[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [saveOpen, setSaveOpen] = useState(false)
  const [replays, setReplays] = useState<Record<string, { state: 'running' | 'done' | 'error'; result?: ReplayResult; message?: string }>>({})
  const [exportFor, setExportFor] = useState<{ id: string; result?: ExportInvariantResponse; error?: string; state: 'running' | 'done' | 'error' } | null>(null)

  const refresh = useCallback(() => {
    api
      .listRegressions()
      .then((l) => {
        setList([...l].sort((a, b) => (b.created_at ?? '').localeCompare(a.created_at ?? '')))
        setError(null)
      })
      .catch((err) => setError(errorMessage(err)))
  }, [])
  useEffect(refresh, [refresh])

  async function replay(id: string) {
    setReplays((r) => ({ ...r, [id]: { state: 'running' } }))
    try {
      const res = await api.replayRegression(id, { trials: 1, timeout: draft.timeoutSec })
      setReplays((r) => ({ ...r, [id]: { state: 'done', result: res } }))
    } catch (err) {
      setReplays((r) => ({ ...r, [id]: { state: 'error', message: errorMessage(err) } }))
    }
  }

  async function remove(id: string) {
    try {
      await api.deleteRegression(id)
      refresh()
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  /** The CI test is only honest when every number comes from a real result:
   *  the threshold search's safe value, or the regression's own environment. */
  async function exportTest(reg: RegressionArtifact) {
    setExportFor({ id: reg.regression_id, state: 'running' })
    const env = reg.environment
    const latency = Number(getField(env, 'network.latency_ms')?.value ?? 0)
    const loss = Number(getField(env, 'network.packet_loss_percent')?.value ?? 0)
    const quota = Number(getField(env, 'cpu.quota_percent')?.value ?? 0)
    const thresholdIsLatency = lastThreshold && lastThresholdParam === 'network.latency_ms' && lastThreshold.outcome === 'boundary_found'
    try {
      const res = await api.exportInvariant({
        project_name: String(reg.metadata.project ?? draft.project?.name ?? reg.regression_id),
        command: reg.command,
        param_name: thresholdIsLatency ? 'network.latency_ms' : latency > 0 ? 'network.latency_ms' : 'network.packet_loss_percent',
        safe_latency_ms: thresholdIsLatency ? (lastThreshold!.safe_value ?? lastThreshold!.credible_low ?? latency) : latency,
        // The exporter takes packet loss in percent (morph/engine/exporter.py).
        safe_packet_loss: loss,
        safe_cpu_quota: quota > 0 ? quota / 100 : 1,
        boundary_estimate: thresholdIsLatency ? lastThreshold!.boundary_estimate : null,
        divergence_summary: typeof reg.metadata.summary === 'string' ? reg.metadata.summary : null,
      })
      setExportFor({ id: reg.regression_id, state: 'done', result: res })
    } catch (err) {
      setExportFor({ id: reg.regression_id, state: 'error', error: errorMessage(err) })
    }
  }

  const canSave = Boolean(draft.profile && draft.command.trim())

  return (
    <>
      <header className="page__head">
        <div>
          <h1>Regressions</h1>
          <p>A saved verdict: the environment, the command and what is expected. Replay it any time, or export it as a CI test.</p>
        </div>
        <div className="page__actions">
          <button className="btn btn--primary" onClick={() => setSaveOpen(true)} disabled={!canSave} title={canSave ? undefined : 'Run something first'}>
            <Icon name="bookmark" size={14} /> Save current verdict
          </button>
        </div>
      </header>

      {error && (
        <p className="note" data-tone="fail" role="alert">
          <Icon name="alert" />
          <span>{error}</span>
        </p>
      )}

      {list && list.length === 0 && (
        <div className="empty">
          <h2>Nothing saved yet</h2>
          <p>Run an experiment, then save its verdict here so the failure can be replayed before it ships again.</p>
          <button className="btn" onClick={() => onNavigate('experiment')}>
            Go to Experiment
          </button>
        </div>
      )}

      {list && list.length > 0 && (
        <div className="reg-list">
          {list.map((reg) => {
            const rp = replays[reg.regression_id]
            const meta = reg.metadata ?? {}
            const cls = typeof meta.classification === 'string' ? meta.classification : null
            const exp = exportFor?.id === reg.regression_id ? exportFor : null
            return (
              <article className="reg" key={reg.regression_id} aria-labelledby={`reg-${reg.regression_id}`}>
                <header className="reg__head">
                  <div>
                    <h2 id={`reg-${reg.regression_id}`} className="reg__name">
                      {reg.regression_id}
                    </h2>
                    <p className="small muted">
                      {formatSummary(reg.environment) || 'host defaults'} · <code className="inline-code">{reg.command}</code>
                    </p>
                  </div>
                  <div className="row">
                    {cls && <Chip tone={cls === 'environment_caused' ? 'fail' : cls === 'no_effect' ? 'ok' : 'warn'}>{cls.replace(/_/g, ' ')}</Chip>}
                    <span className="small faint">{fmtDate(reg.created_at)}</span>
                  </div>
                </header>
                <dl className="kv kv--inline">
                  <div>
                    <dt>Expects</dt>
                    <dd>
                      exit {reg.expected_exit_code} · at most {fmtRate(reg.expected_max_failure_rate)} failures
                    </dd>
                  </div>
                  {reg.failure_signature && (
                    <div>
                      <dt>Signature</dt>
                      <dd>{reg.failure_signature}</dd>
                    </div>
                  )}
                  {typeof meta.strongest_condition === 'string' && meta.strongest_condition && (
                    <div>
                      <dt>Strongest</dt>
                      <dd>{meta.strongest_condition.replace(/_/g, ' ')}</dd>
                    </div>
                  )}
                </dl>
                <div className="row">
                  <button className="btn btn--sm" onClick={() => replay(reg.regression_id)} disabled={rp?.state === 'running'}>
                    <Icon name="play" size={13} /> {rp?.state === 'running' ? 'Replaying…' : 'Replay'}
                  </button>
                  <button className="btn btn--sm" onClick={() => exportTest(reg)} disabled={exp?.state === 'running'}>
                    <Icon name="terminal" size={13} /> Export CI test
                  </button>
                  <button className="btn btn--ghost btn--icon btn--sm" onClick={() => remove(reg.regression_id)} aria-label={`Delete ${reg.regression_id}`}>
                    <Icon name="trash" size={13} />
                  </button>
                </div>
                {rp?.state === 'error' && <p className="field__error">{rp.message}</p>}
                {rp?.state === 'done' && rp.result && (
                  <p className="note" data-tone={rp.result.matches_expected ? 'ok' : 'fail'} role="status">
                    <Icon name={rp.result.matches_expected ? 'check' : 'x'} />
                    <span>
                      {rp.result.matches_expected ? 'Behaves as expected' : 'Does not match the expectation'} · {rp.result.failures}/{rp.result.total_runs} failed ({fmtRate(rp.result.failure_rate)}).{' '}
                      {rp.result.summary}
                    </span>
                  </p>
                )}
                {exp?.state === 'error' && <p className="field__error">{exp.error}</p>}
                {exp?.state === 'done' && exp.result && (
                  <div className="stack">
                    <p className="small muted">{exp.result.summary}</p>
                    <CodeBlock code={exp.result.code} filename={exp.result.filename} maxHeight={280} />
                  </div>
                )}
              </article>
            )
          })}
        </div>
      )}

      <SaveDialog
        open={saveOpen}
        onClose={() => setSaveOpen(false)}
        onSaved={() => {
          setSaveOpen(false)
          refresh()
        }}
        defaults={{
          id: slug(`${draft.project?.name ?? 'run'}-${lastExperiment?.classification ?? (lastRun ? (lastRun.passed ? 'pass' : 'fail') : 'env')}-${new Date().toISOString().slice(0, 10)}`),
          expectedExit: lastRun && !lastRun.passed ? lastRun.exit_code : lastExperiment ? 1 : 0,
          expectedMaxFailureRate: lastExperiment ? 1 : lastRun ? (lastRun.passed ? 0 : 1) : 0,
          signature: lastRun?.error_type ?? null,
          classification: lastExperiment?.classification ?? null,
          strongest: lastExperiment?.strongest_condition ?? null,
          summary: lastExperiment?.summary ?? null,
          thresholdBoundary: lastThreshold?.boundary_estimate ?? null,
          thresholdParam: lastThresholdParam,
        }}
      />
    </>
  )
}

function SaveDialog({
  open,
  onClose,
  onSaved,
  defaults,
}: {
  open: boolean
  onClose: () => void
  onSaved: () => void
  defaults: {
    id: string
    expectedExit: number
    expectedMaxFailureRate: number
    signature: string | null
    classification: string | null
    strongest: string | null
    summary: string | null
    thresholdBoundary: number | null
    thresholdParam: string | null
  }
}) {
  const { draft } = useRunDraft()
  const [id, setId] = useState(defaults.id)
  const [exit, setExit] = useState(String(defaults.expectedExit))
  const [rate, setRate] = useState(String(Math.round(defaults.expectedMaxFailureRate * 100)))
  const [signature, setSignature] = useState(defaults.signature ?? '')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => {
    if (open) {
      setId(defaults.id)
      setExit(String(defaults.expectedExit))
      setRate(String(Math.round(defaults.expectedMaxFailureRate * 100)))
      setSignature(defaults.signature ?? '')
      setErr(null)
    }
    // reset on open only
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  const validId = /^[A-Za-z0-9._-]{1,64}$/.test(id) && id !== '.' && id !== '..'

  async function save() {
    if (!draft.profile) return
    setBusy(true)
    setErr(null)
    try {
      await api.createRegression({
        regression_id: id,
        environment: draft.profile,
        command: draft.command.trim(),
        expected_exit_code: Number(exit) || 0,
        expected_max_failure_rate: Math.min(1, Math.max(0, Number(rate) / 100 || 0)),
        failure_signature: signature.trim() || null,
        metadata: {
          project: draft.project?.name ?? null,
          project_path: draft.project?.path ?? null,
          cwd: draft.cwd,
          classification: defaults.classification,
          strongest_condition: defaults.strongest,
          summary: defaults.summary,
          threshold_parameter: defaults.thresholdParam,
          threshold_boundary: defaults.thresholdBoundary,
          saved_from: 'dashboard',
        },
      })
      onSaved()
    } catch (e) {
      setErr(errorMessage(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onClose={onClose} title="Save as regression">
      <p className="small muted">
        Environment: {draft.profile ? formatSummary(draft.profile, draft.hostProfile) || 'host defaults' : '—'} · <code className="inline-code">{draft.command}</code>
      </p>
      {defaults.classification && (
        <p className="small muted">
          Verdict: {defaults.classification.replace(/_/g, ' ')}
          {defaults.strongest ? ` · strongest ${defaults.strongest.replace(/_/g, ' ')}` : ''}
          {defaults.thresholdBoundary != null ? ` · boundary ≈ ${fmtNumber(defaults.thresholdBoundary)}` : ''}
        </p>
      )}
      <div className="field">
        <label htmlFor="reg-id">Name</label>
        <input id="reg-id" className="input" value={id} onChange={(e) => setId(e.target.value)} aria-invalid={!validId} spellCheck={false} />
        {!validId && <span className="field__error">Letters, digits, dots, dashes and underscores only (max 64).</span>}
      </div>
      <div className="row">
        <div className="field">
          <label htmlFor="reg-exit">Expected exit code</label>
          <input id="reg-exit" className="input input--number" type="number" value={exit} onChange={(e) => setExit(e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="reg-rate">Max failure rate (%)</label>
          <input id="reg-rate" className="input input--number" type="number" min={0} max={100} value={rate} onChange={(e) => setRate(e.target.value)} />
        </div>
      </div>
      <div className="field">
        <label htmlFor="reg-sig">Failure signature (optional)</label>
        <input id="reg-sig" className="input" value={signature} onChange={(e) => setSignature(e.target.value)} placeholder="TimeoutException" />
      </div>
      {err && <p className="field__error">{err}</p>}
      <div className="row" style={{ justifyContent: 'flex-end' }}>
        <button className="btn btn--ghost" onClick={onClose}>
          Cancel
        </button>
        <button className="btn btn--primary" onClick={save} disabled={busy || !validId}>
          {busy ? 'Saving…' : 'Save'}
        </button>
      </div>
    </Dialog>
  )
}
