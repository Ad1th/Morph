import { useId, useState } from 'react'
import type { ThresholdResult } from '../../api/types'
import { fmtNumber, fmtRate } from '../../lib/format'

interface Probe {
  value: number
  passed: boolean
}

/** P(fail | x) along the searched range with the credible band and every
 *  probe (pass low, fail high). Draws the live posterior while searching. */
export function DoseResponseChart({
  low,
  high,
  unit,
  probes,
  result,
  liveLow,
  liveHigh,
  liveMedian,
  paramName,
}: {
  low: number
  high: number
  unit: string
  probes: Probe[]
  result: ThresholdResult | null
  liveLow?: number | null
  liveHigh?: number | null
  liveMedian?: number | null
  paramName: string
}) {
  const id = useId()
  const [hover, setHover] = useState<{ x: number; value: number; p: number | null } | null>(null)
  const W = 640
  const H = 220
  const pad = { l: 44, r: 16, t: 14, b: 34 }
  const iw = W - pad.l - pad.r
  const ih = H - pad.t - pad.b
  const span = high - low || 1
  const px = (v: number) => pad.l + ((v - low) / span) * iw
  const py = (p: number) => pad.t + (1 - p) * ih

  const curve = result?.dose_response ?? []
  const path = curve.length
    ? curve.map((pt, i) => `${i === 0 ? 'M' : 'L'}${px(pt.value).toFixed(1)},${py(pt.failure_probability).toFixed(1)}`).join(' ')
    : ''
  const found = result?.outcome === 'boundary_found'
  const bandLo = found ? result?.credible_low : liveLow
  const bandHi = found ? result?.credible_high : liveHigh
  const median = found ? result?.boundary_estimate : liveMedian

  const xTicks = 5
  const yTicks = [0, 0.25, 0.5, 0.75, 1]

  function onMove(e: React.MouseEvent<SVGSVGElement>) {
    const rect = e.currentTarget.getBoundingClientRect()
    const sx = ((e.clientX - rect.left) / rect.width) * W
    if (sx < pad.l || sx > W - pad.r) return setHover(null)
    const value = low + ((sx - pad.l) / iw) * span
    let p: number | null = null
    if (curve.length) {
      const nearest = curve.reduce((a, b) => (Math.abs(b.value - value) < Math.abs(a.value - value) ? b : a))
      p = nearest.failure_probability
    }
    setHover({ x: sx, value, p })
  }

  return (
    <figure className="dose">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="dose__svg"
        role="img"
        aria-labelledby={`${id}-title`}
        onMouseMove={onMove}
        onMouseLeave={() => setHover(null)}
      >
        <title id={`${id}-title`}>
          Failure probability against {paramName}: {probes.length} probes
        </title>
        {yTicks.map((t) => (
          <g key={t}>
            <line x1={pad.l} x2={W - pad.r} y1={py(t)} y2={py(t)} className="dose__grid" />
            <text x={pad.l - 8} y={py(t) + 4} textAnchor="end" className="dose__tick">
              {Math.round(t * 100)}%
            </text>
          </g>
        ))}
        {Array.from({ length: xTicks + 1 }).map((_, i) => {
          const v = low + (span * i) / xTicks
          return (
            <text key={i} x={px(v)} y={H - 12} textAnchor="middle" className="dose__tick">
              {fmtNumber(v)}
            </text>
          )
        })}
        <text x={W - pad.r} y={H - 1} textAnchor="end" className="dose__tick">
          {unit}
        </text>

        {bandLo != null && bandHi != null && (
          <rect
            x={px(bandLo)}
            y={pad.t}
            width={Math.max(1, px(bandHi) - px(bandLo))}
            height={ih}
            className="dose__band"
          />
        )}
        {median != null && <line x1={px(median)} x2={px(median)} y1={pad.t} y2={pad.t + ih} className="dose__median" />}

        {path && <path d={path} className="dose__curve" />}

        {probes.map((p, i) => (
          <circle
            key={i}
            cx={px(p.value)}
            cy={p.passed ? py(0) - 6 : py(1) + 6}
            r={4}
            className="dose__probe"
            data-passed={p.passed}
          >
            <title>
              {fmtNumber(p.value)} {unit}: {p.passed ? 'passed' : 'failed'}
            </title>
          </circle>
        ))}

        {hover && (
          <g>
            <line x1={hover.x} x2={hover.x} y1={pad.t} y2={pad.t + ih} className="dose__cross" />
            <rect x={Math.min(hover.x + 8, W - 150)} y={pad.t + 4} width={138} height={hover.p != null ? 40 : 24} rx={4} className="dose__tip" />
            <text x={Math.min(hover.x + 16, W - 142)} y={pad.t + 20} className="dose__tiptext">
              {fmtNumber(hover.value)} {unit}
            </text>
            {hover.p != null && (
              <text x={Math.min(hover.x + 16, W - 142)} y={pad.t + 36} className="dose__tiptext">
                P(fail) {fmtRate(hover.p)}
              </text>
            )}
          </g>
        )}
      </svg>
      <figcaption className="dose__legend small muted">
        <span>
          <i className="dose__key dose__key--pass" /> passed probe
        </span>
        <span>
          <i className="dose__key dose__key--fail" /> failed probe
        </span>
        <span>
          <i className="dose__key dose__key--band" /> credible interval
        </span>
        <span>
          <i className="dose__key dose__key--curve" /> P(fail)
        </span>
      </figcaption>
    </figure>
  )
}
