import { useCallback, useEffect, useState } from 'react'
import { api, errorMessage } from '../api/client'
import { getField, setFieldValue } from '../api/profileFields'
import type { EnvironmentProfile, ParameterMetadata, ProjectInfo } from '../api/types'
import { getState, updateDraft, useStore, type RunDraft } from './store'

/** Bundles a preset writes into the network section (ui-spec §4 plus the
 *  product's own operating points). `null` means "leave the host value". */
export const PRESETS: { id: string; label: string; hint: string; values: Record<string, number | null> }[] = [
  { id: 'host', label: 'This machine', hint: 'Every parameter at its detected value', values: {} },
  {
    id: 'flagship',
    label: 'Flagship fault',
    hint: '120 ms latency and 18 % loss: the pair that breaks apps/pool_retry',
    values: { 'network.latency_ms': 120, 'network.packet_loss_percent': 18 },
  },
  {
    id: 'high-latency',
    label: 'High latency',
    hint: '400 ms round trips, clean line',
    values: { 'network.latency_ms': 400, 'network.packet_loss_percent': 0, 'network.jitter_ms': 40 },
  },
  {
    id: 'constrained',
    label: 'Constrained device',
    hint: '2 cores, 2 GiB, 3G-class network',
    values: {
      'cpu.cores': 2,
      'memory.total_mb': 2048,
      'network.latency_ms': 150,
      'network.packet_loss_percent': 1.5,
      'network.bandwidth_mbps': 3,
      'network.jitter_ms': 40,
    },
  },
]

export function applyPreset(profile: EnvironmentProfile, host: EnvironmentProfile | null, id: string): EnvironmentProfile {
  const preset = PRESETS.find((p) => p.id === id)
  if (!preset) return profile
  let next = host ? structuredClone(host) : profile
  if (id === 'host') return next
  for (const [path, value] of Object.entries(preset.values)) {
    if (value == null) continue
    next = setFieldValue(next, path, value, 'requested')
  }
  return next
}

/** The persisted run draft plus the helpers every screen needs to edit it.
 *  Captures the host once on first use so the draft always has a base. */
export function useRunDraft() {
  const draft = useStore((s) => s.draft)
  const [capturing, setCapturing] = useState(false)
  const [captureError, setCaptureError] = useState<string | null>(null)

  const capture = useCallback(async (resetProfile: boolean) => {
    setCapturing(true)
    setCaptureError(null)
    try {
      const host = await api.captureProfile()
      updateDraft((d) => ({
        hostProfile: host,
        profile: resetProfile || !d.profile ? structuredClone(host) : d.profile,
        presetName: resetProfile ? 'host' : d.presetName,
      }))
    } catch (err) {
      setCaptureError(errorMessage(err))
    } finally {
      setCapturing(false)
    }
  }, [])

  useEffect(() => {
    if (!getState().draft.hostProfile && !capturing) void capture(false)
    // capture() is stable; run once on mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const setField = useCallback((path: string, value: unknown) => {
    updateDraft((d) => (d.profile ? { profile: setFieldValue(d.profile, path, value, 'requested'), presetName: null } : {}))
  }, [])

  const resetField = useCallback((path: string) => {
    updateDraft((d) => {
      if (!d.profile) return {}
      const host = d.hostProfile ? getField(d.hostProfile, path) : undefined
      return { profile: setFieldValue(d.profile, path, host?.value ?? null, 'captured'), presetName: null }
    })
  }, [])

  const setProfile = useCallback((profile: EnvironmentProfile) => {
    updateDraft({ profile, presetName: null })
  }, [])

  const choosePreset = useCallback((id: string) => {
    updateDraft((d) => (d.profile ? { profile: applyPreset(d.profile, d.hostProfile, id), presetName: id } : {}))
  }, [])

  const setProject = useCallback((project: ProjectInfo | null) => {
    updateDraft({
      project,
      command: project?.suggested_command ?? '',
      cwd: project?.suggested_cwd ?? null,
    })
  }, [])

  const set = useCallback((patch: Partial<RunDraft>) => updateDraft(patch), [])

  return { draft, capturing, captureError, capture, setField, resetField, setProfile, choosePreset, setProject, set }
}

/** Upper bound for a slider whose catalog `max` is resolved against the host. */
export function resolveMax(meta: ParameterMetadata, host: EnvironmentProfile | null, profile: EnvironmentProfile | null): number {
  if (meta.max != null) return meta.max
  const hv = (path: string) => Number((host && getField(host, path)?.value) ?? NaN)
  switch (meta.field_path) {
    case 'cpu.cores':
      return hv('cpu.logical_processors') || hv('cpu.cores') || 64
    case 'cpu.quota_percent': {
      const cores = Number((profile && getField(profile, 'cpu.cores')?.value) ?? hv('cpu.cores'))
      return (cores || 1) * 100
    }
    case 'memory.total_mb':
      return hv('memory.total_mb') || 65536
    case 'filesystem.disk_space_limit_mb':
      return hv('filesystem.disk_space_limit_mb') || 1048576
    default:
      return 100
  }
}
