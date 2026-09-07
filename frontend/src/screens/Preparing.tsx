import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { EnvironmentProfile, RunResult } from '../api/types'
import type { OsName } from '../theme/useOsTheme'
import './Preparing.css'

type StepState = 'pending' | 'ok' | 'failed'

// docs/ui-spec.md section 9 screen 6's checklist, plus a dependency-download
// step. The real work (apply conditions -> run -> cleanup) happens in one
// RuntimeController.run() call with no granular per-step progress API today,
// so the checklist advances on a short timer while that call is in flight.
// ponytail: cosmetic pacing, not a lie -- every step it shows genuinely
// happens server-side as part of the run, just not individually timed.
// Real per-step progress would need the /run path to emit events the way
// /ws/experiment/{id} already does for experiments.
const STEPS = ['CPU', 'Memory', 'Network', 'Locale', 'Filesystem', 'Dependencies', 'Starting application']

export function Preparing({
  os,
  profile,
  command,
  cwd,
  target,
  onDone,
}: {
  os: OsName
  profile: EnvironmentProfile
  /** The user's project command, confirmed (and editable) on the config screen. */
  command: string
  cwd?: string
  target: string
  onDone: (result: RunResult) => void
}) {
  const [stepStates, setStepStates] = useState<StepState[]>(STEPS.map(() => 'pending'))

  useEffect(() => {
    // No "already started" ref guard: under React StrictMode's dev-only
    // double-invoke, that pattern deadlocks the run -- the discarded first
    // invocation's cleanup sets its own `cancelled` true, the guard then
    // blocks the second (kept) invocation from ever starting a fresh call,
    // and the original promise resolves into a closure that's already
    // cancelled. Letting each invocation own its own `cancelled` flag is the
    // standard fix: in prod (no StrictMode double-invoke) this still runs
    // exactly once.
    let cancelled = false
    let i = 0
    const tick = setInterval(() => {
      if (i >= STEPS.length - 1 || cancelled) {
        clearInterval(tick)
        return
      }
      setStepStates((prev) => prev.map((s, idx) => (idx === i ? 'ok' : s)))
      i += 1
    }, 220)

    api
      .run({ command, cwd, target, profile, timeout: 60 })
      .then((result) => {
        if (cancelled) return
        clearInterval(tick)
        setStepStates(STEPS.map(() => 'ok'))
        setTimeout(() => !cancelled && onDone(result), 300)
      })
      .catch((err) => {
        if (cancelled) return
        clearInterval(tick)
        setStepStates((prev) => prev.map((s) => (s === 'ok' ? s : 'failed')))
        onDone({
          run_id: 'error',
          exit_code: -1,
          stdout: '',
          stderr: String(err),
          duration_ms: 0,
          passed: false,
          error_type: 'ClientError',
          error_message: String(err),
          timestamp: new Date().toISOString(),
        })
      })

    return () => {
      cancelled = true
      clearInterval(tick)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <div className="preparing" data-os={os}>
      <div className="preparing__panel">
        <h2 className="preparing__title">Preparing environment</h2>
        <p className="preparing__command">{command}</p>
        <ul className="preparing__list">
          {STEPS.map((step, i) => (
            <li key={step} data-state={stepStates[i]}>
              <span className="preparing__icon">
                {stepStates[i] === 'ok' ? '✓' : stepStates[i] === 'failed' ? '✕' : '…'}
              </span>
              <span>{step === 'Dependencies' ? 'Downloading dependencies' : `Applying: ${step}`}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}
