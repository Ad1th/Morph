import type { EnvironmentProfile, ExperimentResult, ParameterMetadata, RunResult } from './types'

// Vite dev proxy rewrites /api/* -> http://127.0.0.1:8000/* (see vite.config.ts).
const BASE = '/api'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText)
    throw new Error(`${init?.method ?? 'GET'} ${path} failed (${res.status}): ${detail}`)
  }
  return res.json() as Promise<T>
}

export const api = {
  health: () => request<{ status: string; service: string }>('/health'),

  captureProfile: () => request<EnvironmentProfile>('/profiles/capture', { method: 'POST' }),

  getParameterCatalog: () => request<Record<string, ParameterMetadata>>('/parameters'),

  reconcileProfile: (profile: EnvironmentProfile) =>
    request<EnvironmentProfile>('/profiles/reconcile', {
      method: 'POST',
      body: JSON.stringify(profile),
    }),

  run: (payload: {
    command: string
    profile?: EnvironmentProfile
    timeout?: number
    cwd?: string
    force_proxy?: boolean
    env_overrides?: Record<string, string>
  }) => request<RunResult>('/run', { method: 'POST', body: JSON.stringify(payload) }),

  startExperimentStream: (payload: {
    command: string
    target_profile?: EnvironmentProfile
    trials?: number
    timeout_sec?: number
  }) =>
    request<{ experiment_id: string; status: string }>('/experiments/stream', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  getExperiment: (id: string) => request<ExperimentResult>(`/experiments/${id}`),
}

// Open the progress WebSocket for a running experiment. Vite proxies /ws to the
// API in dev; in a bundled deploy it is same-origin.
export function openExperimentSocket(experimentId: string): WebSocket {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  return new WebSocket(`${proto}://${window.location.host}/ws/experiment/${experimentId}`)
}
