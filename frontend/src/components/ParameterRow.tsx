import { useId } from 'react'
import type { ParameterMetadata, ProfileField } from '../api/types'
import { fmtNumber } from '../lib/format'
import { PlatformBadge, StateChip } from './ui/Chips'
import { Icon } from './ui/Icon'

type Kind = 'toggle' | 'range' | 'text'

function inferKind(meta: ParameterMetadata, value: unknown): Kind {
  if (typeof value === 'boolean' || typeof meta.default === 'boolean') return 'toggle'
  if (meta.min != null || meta.max != null || typeof value === 'number') return 'range'
  return 'text'
}

// Latency, bandwidth and RAM span three orders of magnitude (ui-spec §1): the
// slider is log-scaled for them so the interesting band gets the travel.
const LOG_FIELDS = new Set(['network.latency_ms', 'network.bandwidth_mbps', 'memory.total_mb', 'filesystem.disk_space_limit_mb'])

function toSlider(value: number, min: number, max: number, log: boolean): number {
  if (!log) return value
  const lo = Math.log(Math.max(min, 0.1) )
  const hi = Math.log(Math.max(max, 1))
  if (value <= 0) return 0
  return ((Math.log(Math.max(value, 0.1)) - lo) / (hi - lo)) * 1000
}

function fromSlider(pos: number, min: number, max: number, log: boolean, step: number | null | undefined): number {
  if (!log) return pos
  if (pos <= 0) return min
  const lo = Math.log(Math.max(min, 0.1))
  const hi = Math.log(Math.max(max, 1))
  const raw = Math.exp(lo + (pos / 1000) * (hi - lo))
  const s = step && step > 0 ? step : raw >= 100 ? 1 : raw >= 10 ? 0.5 : 0.1
  return Math.min(max, Math.max(min, Math.round(raw / s) * s))
}

export function ParameterRow({
  meta,
  field,
  max,
  support,
  statusDetail,
  hostValue,
  onChange,
  onReset,
}: {
  meta: ParameterMetadata
  field: ProfileField | undefined
  /** Host-resolved upper bound (catalog `max` may be null). */
  max: number
  support: string
  /** Mechanism and detail from /profiles/fidelity, shown on the state chip. */
  statusDetail?: string
  hostValue: unknown
  onChange: (value: unknown) => void
  onReset: () => void
}) {
  const id = useId()
  const value = field?.value ?? meta.default ?? ''
  const status = field?.status ?? 'captured'
  const kind = inferKind(meta, value)
  const disabled = !meta.controllable || support === 'unsupported'
  const min = meta.min ?? 0
  const log = LOG_FIELDS.has(meta.field_path)
  const num = typeof value === 'number' ? value : Number.isFinite(Number(value)) && value !== '' ? Number(value) : null
  const isDefault = status !== 'requested'
  const changed = !isDefault && hostValue != null && hostValue !== value

  return (
    <div className="prow" data-changed={!isDefault}>
      <label className="prow__label" htmlFor={`${id}-ctl`}>
        {meta.name}
        {changed && hostValue != null && (
          <span className="prow__host faint">
            was {typeof hostValue === 'number' ? fmtNumber(hostValue, meta.step) : String(hostValue)}
          </span>
        )}
      </label>

      <div className="prow__control">
        {kind === 'toggle' && (
          <label className="toggle">
            <input
              id={`${id}-ctl`}
              type="checkbox"
              checked={Boolean(value)}
              disabled={disabled}
              onChange={(e) => onChange(e.target.checked)}
            />
            <span className="small">{value ? 'On' : 'Off'}</span>
          </label>
        )}

        {kind === 'range' && (
          <>
            <input
              id={`${id}-ctl`}
              className="range"
              type="range"
              min={log ? 0 : min}
              max={log ? 1000 : max}
              step={log ? 1 : (meta.step ?? (max - min > 100 ? 1 : 'any'))}
              value={num != null ? toSlider(num, min, max, log) : log ? 0 : min}
              disabled={disabled}
              aria-valuemin={min}
              aria-valuemax={max}
              aria-valuenow={num ?? undefined}
              aria-valuetext={num != null ? `${fmtNumber(num, meta.step)} ${meta.unit}` : 'not set'}
              onChange={(e) => onChange(fromSlider(Number(e.target.value), min, max, log, meta.step))}
              style={{ '--fill': `${num != null ? (toSlider(num, min, max, log) - (log ? 0 : min)) / ((log ? 1000 : max) - (log ? 0 : min)) * 100 : 0}%` } as React.CSSProperties}
            />
            <input
              className="input input--number"
              type="number"
              aria-label={`${meta.name} value`}
              min={min}
              max={max}
              step={meta.step ?? 'any'}
              value={num ?? ''}
              disabled={disabled}
              onChange={(e) => {
                if (e.target.value === '') return onChange(null)
                const v = Number(e.target.value)
                if (Number.isFinite(v)) onChange(v)
              }}
              onBlur={(e) => {
                const v = Number(e.target.value)
                if (e.target.value !== '' && Number.isFinite(v)) onChange(Math.min(max, Math.max(min, v)))
              }}
            />
            <span className="prow__unit muted small">{meta.unit}</span>
          </>
        )}

        {kind === 'text' && (
          <input
            id={`${id}-ctl`}
            className="input"
            type="text"
            value={typeof value === 'string' ? value : ''}
            disabled={disabled}
            placeholder={typeof hostValue === 'string' ? hostValue : undefined}
            onChange={(e) => onChange(e.target.value)}
          />
        )}
      </div>

      <div className="prow__meta">
        <StateChip status={status} title={statusDetail} />
        <PlatformBadge support={support} />
        <button
          className="btn btn--ghost btn--icon btn--sm"
          onClick={onReset}
          disabled={isDefault}
          aria-label={`Reset ${meta.name} to detected value`}
          title="Reset to detected"
        >
          <Icon name="refresh" size={13} />
        </button>
      </div>
    </div>
  )
}
