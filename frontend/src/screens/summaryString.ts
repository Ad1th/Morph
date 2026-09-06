import type { EnvironmentProfile } from '../api/types'

// The one shared formatter ui-spec.md section 7 calls for: used on the
// panel's sticky summary bar, environment cards, and the diff view alike.
// Order: CPU, RAM, latency, loss, bandwidth, jitter, locale, timezone.
// Omits params at their default (0 for network fields, unset for the rest).
export function formatSummary(profile: EnvironmentProfile): string {
  const parts: string[] = []

  if (profile.cpu?.cores?.value != null) parts.push(`${profile.cpu.cores.value} cores`)
  if (profile.memory?.total_mb?.value != null) {
    const gib = profile.memory.total_mb.value / 1024
    parts.push(`${gib % 1 === 0 ? gib : gib.toFixed(1)} GiB`)
  }
  const latency = profile.network?.latency_ms?.value
  if (latency) parts.push(`${latency} ms`)
  const loss = profile.network?.packet_loss_percent?.value
  if (loss) parts.push(`${loss}% loss`)
  const bw = profile.network?.bandwidth_mbps?.value
  if (bw) parts.push(`${bw} Mbit/s`)
  const jitter = profile.network?.jitter_ms?.value
  if (jitter) parts.push(`${jitter} ms jitter`)
  if (profile.locale?.locale?.value) parts.push(String(profile.locale.locale.value))
  if (profile.locale?.timezone?.value) parts.push(String(profile.locale.timezone.value))

  return parts.join(' · ')
}
