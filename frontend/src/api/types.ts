// Mirrors morph/schema/profile.py. Kept in sync by hand -- small enough that a
// codegen step would be more ceremony than the thing it replaces.

export type FieldStatus = 'captured' | 'requested' | 'reproduced' | 'approximated' | 'unavailable'

export interface ProfileField<T = unknown> {
  value: T
  status: FieldStatus
}

export interface OSInfo {
  family: ProfileField<string>
  version: ProfileField<string>
  kernel_version?: ProfileField<string> | null
}

export interface CPUInfo {
  architecture: ProfileField<string>
  cores: ProfileField<number>
  logical_processors: ProfileField<number>
  clock_mhz?: ProfileField<number> | null
  quota_percent?: ProfileField<number> | null
}

export interface MemoryInfo {
  total_mb: ProfileField<number>
  swap_mb?: ProfileField<number> | null
  pressure_percent?: ProfileField<number> | null
}

export interface LocaleInfo {
  locale: ProfileField<string>
  timezone: ProfileField<string>
}

export interface FilesystemInfo {
  case_sensitive: ProfileField<boolean>
  filesystem_type?: ProfileField<string> | null
  read_only?: ProfileField<boolean> | null
  disk_space_limit_mb?: ProfileField<number> | null
  disk_read_latency_ms?: ProfileField<number> | null
  disk_write_latency_ms?: ProfileField<number> | null
}

export interface NetworkInfo {
  latency_ms: ProfileField<number>
  packet_loss_percent: ProfileField<number>
  bandwidth_mbps?: ProfileField<number> | null
  jitter_ms?: ProfileField<number> | null
  available?: ProfileField<boolean> | null
  connection_type?: ProfileField<string> | null
}

export interface ProcessInfo {
  timeout_s?: ProfileField<number> | null
  max_processes?: ProfileField<number> | null
  thread_limit?: ProfileField<number> | null
  fd_limit?: ProfileField<number> | null
}

export interface EnvironmentProfile {
  version: string
  os: OSInfo
  cpu: CPUInfo
  memory: MemoryInfo
  locale: LocaleInfo
  filesystem?: FilesystemInfo | null
  network?: NetworkInfo | null
  process?: ProcessInfo | null
  env_vars: Record<string, string>
}

export interface RunResult {
  run_id: string
  exit_code: number
  stdout: string
  stderr: string
  duration_ms: number
  peak_memory_mb?: number | null
  passed: boolean
  error_type?: string | null
  error_message?: string | null
  timestamp: string
}

// Mirrors morph/schema/events.py's TrialEvent. Only the fields the dashboard
// reads are typed narrowly; the rest ride along as optional.
export interface TrialEvent {
  kind:
    | 'phase_start'
    | 'condition_start'
    | 'trial'
    | 'condition_done'
    | 'comparison'
    | 'search_probe'
    | 'verdict'
    | 'phase_done'
  condition: string
  phase: string
  trial_index?: number | null
  total?: number | null
  passed?: boolean | null
  duration_ms?: number | null
  failures_so_far?: number | null
  error_type?: string | null
  failures?: number | null
  failure_rate?: number | null
  p_value?: number | null
  is_significant?: boolean | null
  effect_label?: string | null
  classification?: string | null
  strongest_condition?: string | null
}

export interface ComparisonResult {
  condition_label: string
  baseline_failures: number
  baseline_total: number
  treatment_failures: number
  treatment_total: number
  p_value: number
  is_significant: boolean
  effect_label: string
}

export interface ExperimentResult {
  experiment_id?: string | null
  classification: string
  strongest_condition: string
  summary: string
  comparisons: ComparisonResult[]
  target_profile?: EnvironmentProfile | null
}

// WebSocket frames from /ws/experiment/{id}.
export type ExperimentFrame =
  | { type: 'connected'; experiment_id: string; status: string }
  | ({ type: 'event' } & TrialEvent)
  | { type: 'done'; result: ExperimentResult }
  | { type: 'error'; message: string }

// Mirrors morph/schema/parameters.py's ParameterMetadata.
export interface ParameterMetadata {
  name: string
  field_path: string
  unit: string
  min?: number | null
  max?: number | null
  default?: boolean | number | string | null
  step?: number | null
  detectable: boolean
  controllable: boolean
  experimentable: boolean
  platform_support: Record<string, string>
}
