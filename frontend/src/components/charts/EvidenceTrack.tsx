import { fmtE } from '../../lib/format'

/** Live e-value on a log scale, growing toward the decision line (K/α).
 *  Anytime-valid, so it is honest to show while trials are still running. */
export function EvidenceTrack({
  eValue,
  threshold,
  decisive,
  history,
  label,
}: {
  eValue: number | null
  threshold: number | null
  decisive: boolean
  history: number[]
  label: string
}) {
  const thr = threshold && threshold > 1 ? threshold : 20
  // Domain: 0.1 (evidence for "no difference") to 4× the decision line.
  const lo = Math.log10(0.1)
  const hi = Math.log10(thr * 4)
  const x = (e: number) => ((Math.log10(Math.max(e, 0.1)) - lo) / (hi - lo)) * 100
  const cur = eValue ?? 1
  const start = x(1)
  const end = x(cur)
  const ticks = [0.1, 1, 10, 100, 1000, 10000].filter((t) => t <= thr * 4 && Math.abs(x(t) - x(thr)) > 9)

  return (
    <figure className="evtrack" data-decisive={decisive} aria-label={label}>
      <svg viewBox="0 0 100 18" preserveAspectRatio="none" className="evtrack__svg" role="img" aria-hidden>
        <line x1="0" x2="100" y1="9" y2="9" className="evtrack__axis" />
        {ticks.map((t) => (
          <line key={t} x1={x(t)} x2={x(t)} y1="6" y2="12" className="evtrack__tick" />
        ))}
        <line x1={start} x2={start} y1="3" y2="15" className="evtrack__one" />
        {/* the decision line */}
        <line x1={x(thr)} x2={x(thr)} y1="1" y2="17" className="evtrack__thr" />
        {/* evidence fill: from E=1 toward the line (or back toward 0.1) */}
        <rect
          x={Math.min(start, end)}
          y="7"
          width={Math.abs(end - start)}
          height="4"
          rx="1"
          className="evtrack__fill"
          data-negative={cur < 1}
        />
        {history.map((h, i) => (
          <circle key={i} cx={x(h)} cy="9" r="0.9" className="evtrack__dot" />
        ))}
        <circle cx={end} cy="9" r="1.8" className="evtrack__head" />
      </svg>
      <figcaption className="evtrack__labels">
        {ticks.map((t) => (
          <span key={t} style={{ left: `${x(t)}%` }} className="evtrack__label faint">
            {t >= 1 ? t : t}
          </span>
        ))}
        <span style={{ left: `${x(thr)}%` }} className="evtrack__label evtrack__label--thr">
          {fmtE(thr)}
        </span>
      </figcaption>
    </figure>
  )
}
