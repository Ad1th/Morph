import { toBackendFamily, type OsName } from '../theme/useOsTheme'
import type { ParameterMetadata, ProfileField } from '../api/types'
import { PlatformBadge, StateChip } from './StateChip'
import './ParameterRow.css'

type ControlKind = 'toggle' | 'slider' | 'text'

function inferKind(meta: ParameterMetadata, currentValue: unknown): ControlKind {
  if (typeof currentValue === 'boolean' || typeof meta.default === 'boolean') return 'toggle'
  if (meta.min != null || meta.max != null || typeof currentValue === 'number') return 'slider'
  return 'text'
}

export function ParameterRow({
  paramKey,
  meta,
  field,
  os,
  onChange,
  onReset,
}: {
  paramKey: string
  meta: ParameterMetadata
  field: ProfileField | undefined
  os: OsName
  onChange: (value: unknown) => void
  onReset: () => void
}) {
  const value = field?.value ?? meta.default ?? ''
  const status = field?.status ?? 'unavailable'
  const kind = inferKind(meta, value)
  const support = meta.platform_support[toBackendFamily(os)] ?? 'unsupported'
  const disabled = !meta.controllable

  return (
    <div className="param-row" data-testid={`param-${paramKey}`}>
      <span className="param-row__label" title={meta.field_path}>
        {meta.name}
      </span>

      <div className="param-row__control">
        {kind === 'toggle' && (
          <label className="param-row__toggle">
            <input
              type="checkbox"
              checked={Boolean(value)}
              disabled={disabled}
              onChange={(e) => onChange(e.target.checked)}
            />
            <span>{value ? 'On' : 'Off'}</span>
          </label>
        )}

        {kind === 'slider' && (
          <div className="param-row__slider">
            {/* A range input needs a real ceiling, and only some parameters
                have one. This used to fall back to max=100, which invented
                hardware -- offering 100 cores on a 16-core host -- and, where
                the minimum was already 100 (disk space, in MiB), produced a
                slider pinned shut with min === max. Where the catalog knows no
                maximum, there is simply no slider, and the number field below
                takes the value on its own. */}
            {meta.max != null && (
              <input
                type="range"
                min={meta.min ?? 0}
                max={meta.max}
                step={meta.step ?? 1}
                value={typeof value === 'number' ? value : Number(meta.min ?? 0)}
                disabled={disabled}
                onChange={(e) => onChange(Number(e.target.value))}
              />
            )}
            <input
              type="number"
              className="param-row__number"
              min={meta.min ?? undefined}
              max={meta.max ?? undefined}
              step={meta.step ?? 1}
              value={typeof value === 'number' ? value : ''}
              disabled={disabled}
              onChange={(e) => onChange(e.target.value === '' ? null : Number(e.target.value))}
            />
            {meta.unit && <span className="param-row__unit">{meta.unit}</span>}
          </div>
        )}

        {kind === 'text' && (
          <input
            type="text"
            className="param-row__text"
            value={typeof value === 'string' ? value : ''}
            disabled={disabled}
            onChange={(e) => onChange(e.target.value)}
          />
        )}
      </div>

      <StateChip status={status} />
      <PlatformBadge support={support} />
      <button className="param-row__reset" title="Reset to default" onClick={onReset} aria-label="Reset">
        ↺
      </button>
    </div>
  )
}
