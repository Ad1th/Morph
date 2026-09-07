import { useEffect, useMemo, useRef, useState } from 'react'
import { api, openExperimentSocket } from '../api/client'
import type {
  EnvironmentProfile,
  ExperimentFrame,
  ExperimentResult,
  TrialEvent,
} from '../api/types'
import type { OsName } from '../theme/useOsTheme'
import './Experiment.css'

type Lane = {
  condition: string
  total: number
  trials: boolean[]
  failures: number
  done: boolean
  pValue: number | null
  effect: string | null
  significant: boolean | null
}

const DEMO_COMMAND = 'python -m apps.pool_retry test'
const DEFAULT_LATENCY_MS = 120
const DEFAULT_LOSS_PCT = 18
const DEFAULT_TRIALS = 12

function withNetwork(
  profile: EnvironmentProfile,
  latencyMs: number,
  lossPct: number,
): EnvironmentProfile {
  return {
    ...profile,
    network: {
      latency_ms: { value: latencyMs, status: 'requested' },
      packet_loss_percent: { value: lossPct, status: 'requested' },
      bandwidth_mbps: null,
      jitter_ms: null,
      available: null,
      connection_type: null,
    },
  }
}

function emptyLane(condition: string, total: number): Lane {
  return {
    condition,
    total,
    trials: [],
    failures: 0,
    done: false,
    pValue: null,
    effect: null,
    significant: null,
  }
}

export function Experiment({ os, onBack }: { os: OsName; onBack: () => void }) {
  const [status, setStatus] = useState<'starting' | 'running' | 'done' | 'error'>('starting')
  const [message, setMessage] = useState('Capturing this machine…')
  const [lanes, setLanes] = useState<Record<string, Lane>>({})
  const [order, setOrder] = useState<string[]>([])
  const [phase, setPhase] = useState<string>('')
  const [result, setResult] = useState<ExperimentResult | null>(null)
  const socketRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    let cancelled = false
    let ws: WebSocket | null = null

    function applyEvent(ev: TrialEvent) {
      if (ev.phase && (ev.kind === 'phase_start' || ev.kind === 'phase_done')) {
        setPhase(ev.kind === 'phase_start' ? ev.phase : '')
        return
      }
      const cond = ev.condition
      if (!cond) return

      setLanes((prev) => {
        const lane = prev[cond] ? { ...prev[cond] } : emptyLane(cond, ev.total ?? 0)
        if (ev.total != null) lane.total = ev.total
        if (ev.kind === 'trial') {
          lane.trials = [...lane.trials, ev.passed === true]
          if (ev.passed === false) lane.failures += 1
        } else if (ev.kind === 'condition_done') {
          lane.done = true
          if (ev.failures != null) lane.failures = ev.failures
        } else if (ev.kind === 'comparison') {
          lane.pValue = ev.p_value ?? lane.pValue
          lane.effect = ev.effect_label ?? lane.effect
          lane.significant = ev.is_significant ?? lane.significant
        }
        return { ...prev, [cond]: lane }
      })
      setOrder((prev) => (prev.includes(cond) ? prev : [...prev, cond]))
    }

    function handleFrame(frame: ExperimentFrame) {
      if (cancelled) return
      switch (frame.type) {
        case 'connected':
          break
        case 'event':
          applyEvent(frame)
          break
        case 'done':
          setResult(frame.result)
          setStatus('done')
          setMessage('')
          setPhase('')
          break
        case 'error':
          setStatus('error')
          setMessage(frame.message)
          break
      }
    }

    ;(async () => {
      try {
        const host = await api.captureProfile()
        if (cancelled) return
        const profile = withNetwork(host, DEFAULT_LATENCY_MS, DEFAULT_LOSS_PCT)
        setMessage('Starting experiment…')
        const { experiment_id } = await api.startExperimentStream({
          command: DEMO_COMMAND,
          target_profile: profile,
          trials: DEFAULT_TRIALS,
          timeout_sec: 30,
        })
        if (cancelled) return
        setStatus('running')
        setMessage('')
        ws = openExperimentSocket(experiment_id)
        socketRef.current = ws
        ws.onmessage = (e) => {
          try {
            handleFrame(JSON.parse(e.data) as ExperimentFrame)
          } catch {
            /* ignore non-JSON keepalives */
          }
        }
        ws.onerror = () => {
          if (!cancelled && status !== 'done') {
            setStatus('error')
            setMessage('Lost connection to the experiment stream.')
          }
        }
      } catch (err) {
        if (!cancelled) {
          setStatus('error')
          setMessage(String(err))
        }
      }
    })()

    return () => {
      cancelled = true
      ws?.close()
      socketRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const laneList = useMemo(() => order.map((c) => lanes[c]).filter(Boolean), [order, lanes])

  return (
    <div className="experiment" data-os={os}>
      <div className="experiment__panel">
        <header className="experiment__head">
          <h2 className="experiment__title">Causal isolation</h2>
          <span className="experiment__status" data-status={status}>
            {status === 'running' && phase ? `${status} · ${phase}` : status}
          </span>
        </header>

        {message && <p className="experiment__message">{message}</p>}

        <div className="experiment__lanes">
          {laneList.map((lane) => (
            <LaneRow key={lane.condition} lane={lane} />
          ))}
          {laneList.length === 0 && status !== 'error' && (
            <p className="experiment__message">Waiting for the first trials…</p>
          )}
        </div>

        {result && <VerdictCard result={result} />}

        <button className="experiment__back" onClick={onBack}>
          ← Back
        </button>
      </div>
    </div>
  )
}

function LaneRow({ lane }: { lane: Lane }) {
  const ran = lane.trials.length
  const rate = ran ? lane.failures / ran : 0
  return (
    <div className="lane" data-done={lane.done}>
      <div className="lane__top">
        <span className="lane__name">{lane.condition}</span>
        <span className="lane__count">
          {lane.failures}/{ran || lane.total} failed
        </span>
        {lane.significant != null && (
          <span className="lane__stat" data-sig={lane.significant}>
            {lane.pValue != null ? `p=${lane.pValue.toFixed(4)}` : ''}
            {lane.significant ? '  SIGNIFICANT ↑' : lane.effect ? `  ${lane.effect}` : ''}
          </span>
        )}
      </div>
      <div className="lane__strip">
        {lane.trials.map((passed, i) => (
          <i key={i} className="lane__tick" data-passed={passed} />
        ))}
        {Array.from({ length: Math.max(0, lane.total - ran) }).map((_, i) => (
          <i key={`p${i}`} className="lane__tick" data-pending />
        ))}
      </div>
      <div className="lane__bar">
        <span style={{ width: `${(rate * 100).toFixed(1)}%` }} />
      </div>
    </div>
  )
}

function VerdictCard({ result }: { result: ExperimentResult }) {
  return (
    <div className="verdictcard" data-class={result.classification}>
      <div className="verdictcard__label">{result.classification.replace(/_/g, ' ')}</div>
      {result.strongest_condition && (
        <div className="verdictcard__row">
          strongest condition: <strong>{result.strongest_condition}</strong>
        </div>
      )}
      <p className="verdictcard__summary">{result.summary}</p>
    </div>
  )
}
