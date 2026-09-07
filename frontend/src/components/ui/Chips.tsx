import type { FieldStatus } from '../../api/types'
import { Icon, type IconName } from './Icon'

type Tone = 'ok' | 'warn' | 'fail' | 'accent' | 'gold' | 'solid' | undefined

const STATE: Record<FieldStatus, { label: string; tone: Tone; icon?: IconName }> = {
  captured: { label: 'Detected', tone: undefined },
  requested: { label: 'Requested', tone: 'accent' },
  reproduced: { label: 'Reproduced', tone: 'ok', icon: 'check' },
  approximated: { label: 'Approximated', tone: 'warn', icon: 'alert' },
  unavailable: { label: 'Unavailable', tone: 'fail', icon: 'x' },
}

/** What Morph did (or will do) with a field's value. */
export function StateChip({ status, title }: { status: FieldStatus; title?: string }) {
  const s = STATE[status] ?? STATE.captured
  return (
    <span className="chip" data-tone={s.tone} title={title}>
      {s.icon && <Icon name={s.icon} size={11} />}
      {s.label}
    </span>
  )
}

const SUPPORT: Record<string, { label: string; icon: IconName; tone: Tone }> = {
  local: { label: 'local', icon: 'check', tone: undefined },
  approx: { label: 'approx', icon: 'alert', tone: 'warn' },
  worker: { label: 'worker', icon: 'cloud', tone: undefined },
  unsupported: { label: 'unsupported', icon: 'x', tone: undefined },
}

/** Whether Morph can control this field on the chosen target. */
export function PlatformBadge({ support }: { support: string }) {
  const s = SUPPORT[support] ?? { label: support, icon: 'info' as IconName, tone: undefined }
  return (
    <span className="chip" data-tone={s.tone} title={`Platform support: ${s.label}`}>
      <Icon name={s.icon} size={11} />
      {s.label}
    </span>
  )
}

export function Chip({ tone, icon, children }: { tone?: Tone; icon?: IconName; children: React.ReactNode }) {
  return (
    <span className="chip" data-tone={tone}>
      {icon && <Icon name={icon} size={11} />}
      {children}
    </span>
  )
}
