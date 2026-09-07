import { useMemo, useState } from 'react'
import { api } from '../api/client'
import type {
  EnvironmentProfile,
  ExportInvariantResponse,
  ParameterMetadata,
  ThresholdResult,
} from '../api/types'
import './ThresholdPanel.css'

/** Binary-searches the value of one numeric parameter at which the run flips
 *  from passing to failing. Wraps POST /threshold. */
export function ThresholdPanel({
  catalog,
  profile,
  command,
  cwd,
  target,
}: {
  catalog: Record<string, ParameterMetadata>
  /** The profile as edited on this screen: it is the base the search varies
      the chosen parameter on top of. */
  profile: EnvironmentProfile
  command: string
  cwd?: string
  target: string
}) {
  // Only numeric parameters can be searched: `min` is set exactly on the ones
  // the catalog treats as a range, so it doubles as the numeric test.
  const numeric = useMemo(
    () => Object.values(catalog).filter((m) => m.experimentable && m.min != null),
    [catalog],
  )

  const [parameter, setParameter] = useState(numeric[0]?.field_path ?? '')
  const [low, setLow] = useState('0')
  const [high, setHigh] = useState('500')
  const [trials, setTrials] = useState('3')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<ThresholdResult | null>(null)
  const [exportResult, setExportResult] = useState<ExportInvariantResponse | null>(null)
  const [copied, setCopied] = useState(false)

  const meta = numeric.find((m) => m.field_path === parameter)
  const canRun =
    !busy &&
    command.trim() !== '' &&
    parameter !== '' &&
    Number.isFinite(Number(low)) &&
    Number.isFinite(Number(high)) &&
    Number(low) < Number(high)

  async function search() {
    setBusy(true)
    setError(null)
    setResult(null)
    try {
      setResult(
        await api.findThreshold({
          command,
          parameter,
          low: Number(low),
          high: Number(high),
          trials: Math.max(1, Number(trials) || 1),
          // The edited profile is the base the search starts from. Sections the
          // host cannot read come back null from /profiles/capture; the backend
          // fills an absent network section in as unconstrained rather than
          // rejecting it.
          profile,
          cwd,
          target,
          timeout: 30,
        }),
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    }
    setBusy(false)
  }

  if (numeric.length === 0) {
    return <p className="threshold__note">No numeric parameters available to search.</p>
  }

  return (
    <div className="threshold">
      <p className="threshold__note">
        Searches between a known-safe low value and a known-failing high value, running the command
        below on top of the parameters set above.
      </p>

      <div className="threshold__fields">
        <label className="threshold__field">
          <span>Parameter</span>
          <select value={parameter} onChange={(e) => setParameter(e.target.value)}>
            {numeric.map((m) => (
              <option key={m.field_path} value={m.field_path}>
                {m.name} ({m.field_path})
              </option>
            ))}
          </select>
        </label>

        <label className="threshold__field threshold__field--narrow">
          <span>Low{meta ? ` (${meta.unit})` : ''}</span>
          <input type="number" value={low} onChange={(e) => setLow(e.target.value)} />
        </label>

        <label className="threshold__field threshold__field--narrow">
          <span>High{meta ? ` (${meta.unit})` : ''}</span>
          <input type="number" value={high} onChange={(e) => setHigh(e.target.value)} />
        </label>

        <label className="threshold__field threshold__field--narrow">
          <span>Trials</span>
          <input
            type="number"
            min={1}
            value={trials}
            onChange={(e) => setTrials(e.target.value)}
          />
        </label>
      </div>

      <button
        className="param-config__btn"
        onClick={search}
        disabled={!canRun}
        title={
          command.trim() === ''
            ? 'Enter a command to run first'
            : Number(low) < Number(high)
              ? undefined
              : 'Low must be less than high'
        }
      >
        {busy ? 'Searching…' : 'Find Threshold'}
      </button>

      {error && <p className="threshold__error">{error}</p>}

      {result && (
        <div className="threshold__result">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
            <p style={{ margin: 0 }}>
              Boundary estimate: <strong>{result.boundary_estimate ?? 'None'}</strong> (safe {result.safe_value ?? 'None'},
              fails at {result.failure_value ?? 'None'})
            </p>
            <button
              className="param-config__btn"
              style={{ fontSize: '0.75rem', padding: '0.3rem 0.6rem', background: '#1f6feb', color: '#fff' }}
              onClick={async () => {
                const exp = await api.exportInvariant({
                  project_name: 'service',
                  command: command.trim(),
                  safe_latency_ms: result.safe_value ?? 160,
                  safe_packet_loss: 0.01,
                  param_name: result.parameter,
                  boundary_estimate: result.boundary_estimate,
                })
                setExportResult(exp)
              }}
            >
              ⚡ Export Invariant Guardrail
            </button>
          </div>
          <table className="threshold__table">
            <thead>
              <tr>
                <th>Value</th>
                <th>Failure rate</th>
                <th>Passed</th>
              </tr>
            </thead>
            <tbody>
              {result.search_points.map((p, i) => (
                <tr key={i}>
                  <td>{p.value ?? '-'}</td>
                  <td>{p.failure_rate ?? '-'}</td>
                  <td>{p.passed === undefined ? '-' : p.passed ? 'yes' : 'no'}</td>
                </tr>
              ))}
            </tbody>
          </table>

          {exportResult && (
            <div style={{ marginTop: '0.75rem', background: '#161b22', border: '1px solid #238636', borderRadius: '6px', padding: '0.75rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                <span style={{ fontSize: '0.8rem', fontWeight: 600, color: '#3fb950' }}>{exportResult.filename}</span>
                <button
                  className="param-config__btn"
                  style={{ fontSize: '0.72rem', padding: '0.2rem 0.5rem' }}
                  onClick={() => {
                    navigator.clipboard.writeText(exportResult.code)
                    setCopied(true)
                    setTimeout(() => setCopied(false), 2000)
                  }}
                >
                  {copied ? '✓ Copied' : 'Copy Code'}
                </button>
              </div>
              <pre style={{ margin: 0, fontSize: '0.72rem', background: '#0d1117', padding: '0.5rem', borderRadius: '4px', maxHeight: '180px', overflowY: 'auto', color: '#79c0ff' }}>
                <code>{exportResult.code}</code>
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
