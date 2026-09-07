import { useMemo, useState } from 'react'
import { api } from '../api/client'
import type { EnvironmentProfile, ParameterMetadata, ThresholdResult } from '../api/types'
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
          <p>
            Boundary estimate: <strong>{result.boundary_estimate}</strong> (safe {result.safe_value},
            fails at {result.failure_value})
          </p>
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
        </div>
      )}
    </div>
  )
}
