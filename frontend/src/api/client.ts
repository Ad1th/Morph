import type {
  EnvironmentProfile,
  ExperimentResult,
  ExperimentStreamRequest,
  ExportInvariantRequest,
  ExportInvariantResponse,
  FidelityEntry,
  GithubRepo,
  MinimizeResult,
  ParameterMetadata,
  PlatformInfo,
  ProjectInfo,
  RegressionArtifact,
  ReplayResult,
  RunResult,
  SavedProfileRef,
  ThresholdRequest,
  ThresholdResult,
} from './types'

// Same origin by default: the Vite dev proxy rewrites /api/* -> 127.0.0.1:8000
// Same origin by default: the Vite dev proxy rewrites /api/* -> 127.0.0.1:8000
// and strips the /api prefix (see vite.config.ts), so a bundled deploy where
// the API is served alongside the static build needs nothing else. Set
// VITE_API_URL (no trailing slash, e.g. https://api.morph.dev) when the
// frontend is deployed separately from the backend — such as the static build
// on Vercel talking to a Morph Fleet worker — and requests go straight to the
// API's real paths (no /api prefix; there is no proxy to strip it for you).
// See frontend/.env.example.
const API_URL = import.meta.env.VITE_API_URL?.replace(/\/+$/, '')
const BASE = API_URL ?? '/api'

/** A failed request, with the backend's `detail` already unwrapped. */
export class ApiError extends Error {
  status: number
  path: string
  constructor(status: number, path: string, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.path = path
  }
  /** 422 from the run/experiment routes: the command could not launch. */
  get isSetupError() {
    return this.status === 422
  }
}

function readDetail(text: string, fallback: string): string {
  try {
    const body = JSON.parse(text) as { detail?: unknown }
    const d = body.detail
    if (typeof d === 'string') return d
    if (Array.isArray(d)) {
      // FastAPI validation errors: [{loc, msg, type}]
      return d
        .map((e) => {
          const loc = Array.isArray(e?.loc) ? e.loc.filter((x: unknown) => x !== 'body').join('.') : ''
          return loc ? `${loc}: ${e?.msg ?? ''}` : String(e?.msg ?? '')
        })
        .join('; ')
    }
    if (d && typeof d === 'object') return JSON.stringify(d)
  } catch {
    /* not JSON */
  }
  return text.trim() || fallback
}

/** Turn any thrown value into a sentence a person can act on. */
export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) return err.message
  if (err instanceof TypeError && /fetch/i.test(err.message)) {
    return 'Could not reach the Morph server. Start it with `morph serve` (or uvicorn morph.api.app:app).'
  }
  if (err instanceof Error) return err.message
  return String(err)
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const isForm = init?.body instanceof FormData
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: isForm ? init?.headers : { 'Content-Type': 'application/json', ...init?.headers },
  })
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new ApiError(res.status, path, readDetail(text, `${res.status} ${res.statusText}`))
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

const json = (body: unknown): RequestInit => ({ method: 'POST', body: JSON.stringify(body) })

export const api = {
  health: () => request<{ status: string; service: string }>('/health'),
  version: () => request<{ version?: string; morph?: string; [k: string]: unknown }>('/version'),

  // --- profiles ---
  captureProfile: () => request<EnvironmentProfile>('/profiles/capture', { method: 'POST' }),
  reconcileProfile: (profile: EnvironmentProfile) =>
    request<EnvironmentProfile>('/profiles/reconcile', json(profile)),
  /** Per-field plan from the active adapter: what will be reproduced,
   *  approximated or left unavailable, and by which mechanism. */
  profileFidelity: (profile: EnvironmentProfile) =>
    request<Record<string, FidelityEntry>>('/profiles/fidelity', json(profile)),
  listProfiles: () => request<SavedProfileRef[]>('/profiles'),
  getProfile: (id: string) => request<EnvironmentProfile>(`/profiles/${encodeURIComponent(id)}`),
  saveProfile: (id: string, profile: EnvironmentProfile, description?: string) =>
    request<{ id: string; status: string; path: string }>('/profiles', json({ id, profile, description })),

  getParameterCatalog: () => request<Record<string, ParameterMetadata>>('/parameters'),
  getPlatform: () => request<PlatformInfo>('/platform'),

  // --- runs ---
  run: (payload: {
    command: string
    profile?: EnvironmentProfile
    timeout?: number
    cwd?: string | null
    target?: string
  }) => request<RunResult>('/run', json(payload)),

  // --- projects ---
  uploadProject: (files: FileList | File[]) => {
    const form = new FormData()
    for (const file of Array.from(files)) form.append('files', file, file.webkitRelativePath || file.name)
    return request<ProjectInfo>('/projects/upload', { method: 'POST', body: form })
  },
  useLocalProject: (path: string, install = false) =>
    request<ProjectInfo>('/projects/local', json({ path, install })),
  useGithubProject: (payload: { repo: string; token?: string; branch?: string; install?: boolean }) =>
    request<ProjectInfo>('/projects/github', json(payload)),
  listProjects: () => request<ProjectInfo[]>('/projects'),
  getProject: (id: string) => request<ProjectInfo>(`/projects/${encodeURIComponent(id)}`),
  updateProject: (id: string, payload: { command?: string | null; cwd?: string | null }) =>
    request<ProjectInfo>(`/projects/${encodeURIComponent(id)}`, { method: 'PUT', body: JSON.stringify(payload) }),
  deleteProject: (id: string) => request<{ deleted: boolean }>(`/projects/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  installProject: (id: string) => request<ProjectInfo>(`/projects/${encodeURIComponent(id)}/install`, { method: 'POST' }),

  // --- github ---
  githubAuthStatus: () => request<{ authenticated: boolean; source: string }>('/projects/github/auth-status'),
  requestGithubDeviceCode: (payload?: { client_id?: string }) =>
    request<{ device_code: string; user_code: string; verification_uri: string; expires_in: number; interval: number }>(
      '/projects/github/device-code',
      json(payload ?? {}),
    ),
  pollGithubDeviceToken: (payload: { device_code: string; client_id?: string }) =>
    request<{ access_token?: string; error?: string; error_description?: string; interval?: number }>(
      '/projects/github/poll-token',
      json(payload),
    ),
  fetchGithubRepos: (token?: string) => request<GithubRepo[]>('/projects/github/repos', json(token ? { token } : {})),

  // --- experiments ---
  startExperimentStream: (payload: ExperimentStreamRequest) =>
    request<{ experiment_id: string; status: string; mode?: string }>('/experiments/stream', json(payload)),
  getExperiment: (id: string) => request<ExperimentResult>(`/experiments/${encodeURIComponent(id)}`),
  cancelExperiment: (id: string) =>
    request<{ experiment_id: string; cancelled: boolean }>(`/experiments/${encodeURIComponent(id)}`, { method: 'DELETE' }),

  // --- threshold ---
  findThreshold: (req: ThresholdRequest) => request<ThresholdResult>('/threshold', json(req)),
  startThresholdStream: (req: ThresholdRequest) =>
    request<{ threshold_id: string; status: string }>('/threshold/stream', json(req)),
  cancelThreshold: (id: string) => request<unknown>(`/threshold/${encodeURIComponent(id)}`, { method: 'DELETE' }),

  // --- minimal failing set ---
  minimize: (payload: {
    command: string
    target_profile: EnvironmentProfile
    cwd?: string | null
    runs?: number
    timeout?: number
  }) => request<MinimizeResult>('/minimize', json(payload)),

  // --- regressions ---
  listRegressions: () => request<RegressionArtifact[]>('/regressions'),
  createRegression: (artifact: RegressionArtifact) =>
    request<{ status: string; regression_id: string; path: string }>('/regressions', json(artifact)),
  replayRegression: (id: string, payload?: { trials?: number; timeout?: number }) =>
    request<ReplayResult>(`/regressions/${encodeURIComponent(id)}/replay`, json(payload ?? { trials: 1 })),
  deleteRegression: (id: string) =>
    request<{ status: string }>(`/regressions/${encodeURIComponent(id)}`, { method: 'DELETE' }),

  exportInvariant: (req: ExportInvariantRequest) =>
    request<ExportInvariantResponse>('/export/invariant', json(req)),
}

/** WebSocket URL for a job. Vite proxies /ws to the API in dev and a bundled
 *  same-origin deploy needs nothing else. When VITE_API_URL points at a separate
 *  host, the socket's host is derived from it (http -> ws, https -> wss). */
export function jobSocketUrl(kind: 'experiment' | 'threshold', id: string): string {
  if (API_URL) {
    return `${API_URL.replace(/^http/, 'ws')}/ws/${kind}/${encodeURIComponent(id)}`
  }
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  return `${proto}://${window.location.host}/ws/${kind}/${encodeURIComponent(id)}`
}
