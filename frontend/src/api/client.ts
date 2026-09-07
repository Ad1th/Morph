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

// Vite dev proxy rewrites /api/* -> http://127.0.0.1:8000/* (see vite.config.ts).
const BASE = '/api'

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

// Open the progress WebSocket for a running experiment. Vite proxies /ws to the
// API in dev; in a bundled deploy it is same-origin.
export function openExperimentSocket(experimentId: string): WebSocket {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  return new WebSocket(`${proto}://${window.location.host}/ws/experiment/${experimentId}`)
}

