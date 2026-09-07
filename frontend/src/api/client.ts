import type {
  DifferentialBlameResult,
  EnvironmentProfile,
  ExperimentResult,
  ExportInvariantRequest,
  ExportInvariantResponse,
  ParameterMetadata,
  PlatformInfo,
  ProjectInfo,
  RunResult,
  SurfaceRequest,
  SurfaceResult,
  ThresholdRequest,
  ThresholdResult,
} from './types'

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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  // Content-Type is conditional: a FormData body must be left alone so the
  // browser can set multipart/form-data plus its own boundary. Forcing
  // application/json here loses the boundary and FastAPI answers 422.
  const isForm = init?.body instanceof FormData
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: isForm ? init?.headers : { 'Content-Type': 'application/json', ...init?.headers },
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
    target?: string
    force_proxy?: boolean
    env_overrides?: Record<string, string>
  }) => request<RunResult>('/run', { method: 'POST', body: JSON.stringify(payload) }),

  /** Each part is sent under the repeated field name `files`, with the part
   *  filename set to the file's path inside the picked folder. */
  uploadProject: (files: FileList | File[]) => {
    const form = new FormData()
    for (const file of Array.from(files)) {
      form.append('files', file, file.webkitRelativePath || file.name)
    }
    return request<ProjectInfo>('/projects/upload', { method: 'POST', body: form })
  },

  useLocalProject: (path: string) =>
    request<ProjectInfo>('/projects/local', { method: 'POST', body: JSON.stringify({ path }) }),

  useGithubProject: (payload: { repo: string; token?: string; branch?: string }) =>
    request<ProjectInfo>('/projects/github', { method: 'POST', body: JSON.stringify(payload) }),

  /** A token from the server's `gh` CLI / environment, so the browser can skip
   *  the device flow when the machine is already authenticated. */
  githubCliToken: () =>
    request<{ token: string | null; source: string }>('/projects/github/cli-token', {
      method: 'POST',
    }),

  listProjects: () => request<ProjectInfo[]>('/projects'),

  /** Build the project an isolated venv and install its dependencies; the
   *  returned project's `suggested_command` runs from that venv. */
  installProject: (projectId: string) =>
    request<ProjectInfo>(`/projects/${projectId}/install`, { method: 'POST' }),

  requestGithubDeviceCode: (payload?: { client_id?: string }) =>
    request<{
      device_code: string
      user_code: string
      verification_uri: string
      expires_in: number
      interval: number
    }>('/projects/github/device-code', { method: 'POST', body: JSON.stringify(payload ?? {}) }),

  pollGithubDeviceToken: (payload: { device_code: string; client_id?: string }) =>
    request<{
      access_token?: string
      error?: string
      error_description?: string
      interval?: number
    }>('/projects/github/poll-token', { method: 'POST', body: JSON.stringify(payload) }),

  fetchGithubRepos: (token: string) =>
    request<
      Array<{
        full_name: string
        name: string
        private: boolean
        default_branch: string
        description: string
        html_url: string
      }>
    >('/projects/github/repos', { method: 'POST', body: JSON.stringify({ token }) }),

  getPlatform: () => request<PlatformInfo>('/platform'),

  findThreshold: (req: ThresholdRequest) =>
    request<ThresholdResult>('/threshold', { method: 'POST', body: JSON.stringify(req) }),

  computeSurface: (req: SurfaceRequest) =>
    request<SurfaceResult>('/surface', { method: 'POST', body: JSON.stringify(req) }),

  analyzeBlame: (req: {
    pass_output: string
    fail_output: string
    pass_param_label?: string
    fail_param_label?: string
    project_path?: string
  }) => request<DifferentialBlameResult>('/blame', { method: 'POST', body: JSON.stringify(req) }),

  exportInvariant: (req: ExportInvariantRequest) =>
    request<ExportInvariantResponse>('/export/invariant', {
      method: 'POST',
      body: JSON.stringify(req),
    }),

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

// Open the progress WebSocket for a running experiment. Vite proxies /ws to
// the API in dev, and a bundled same-origin deploy needs nothing else. When
// VITE_API_URL points at a separate host, derive the socket's host from it
// (http -> ws, https -> wss) instead of window.location.
export function openExperimentSocket(experimentId: string): WebSocket {
  if (API_URL) {
    const wsUrl = API_URL.replace(/^http/, 'ws')
    return new WebSocket(`${wsUrl}/ws/experiment/${experimentId}`)
  }
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  return new WebSocket(`${proto}://${window.location.host}/ws/experiment/${experimentId}`)
}

