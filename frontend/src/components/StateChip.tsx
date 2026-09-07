import type { FieldStatus } from '../api/types'
import './StateChip.css'

const LABELS: Record<FieldStatus, string> = {
  captured: 'Detected',
  requested: 'Requested',
  reproduced: 'Reproduced',
  approximated: 'Approximated',
  unavailable: 'Not detected',
}

export function StateChip({ status }: { status: FieldStatus }) {
  return (
    <span className="state-chip" data-status={status}>
      {LABELS[status]}
    </span>
  )
}

const BADGE_LABELS: Record<string, string> = {
  local: '✓ local',
  approx: '≈ approx',
  worker: '☁ worker',
  unsupported: '✕ unsupported',
}

export function PlatformBadge({ support }: { support: string }) {
  return (
    <span className="platform-badge" data-support={support} title={`Platform support: ${support}`}>
      {BADGE_LABELS[support] ?? support}
    </span>
  )
}
