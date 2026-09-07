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
// --- Project selection (POST /projects/upload, POST /projects/local) ---

export interface ProjectInfo {
  project_id: string
  name: string
  path: string
  file_count: number
  entrypoints: string[]
  /** Null when auto-detection found no entrypoint it recognises. */
  suggested_command?: string | null
  suggested_cwd?: string | null
  /** Install steps that failed (empty = clean, or nothing to install). */
  deps_failed: string[]
}

// --- Run targets (GET /platform) ---

export interface RunTarget {
  id: string
  family: string
  label: string
  available: boolean
  /** Why the target is unavailable, e.g. "No remote host configured". */
  reason?: string | null
  capabilities: Record<string, boolean>
}

export interface PlatformInfo {
  host: { family: string; version: string; arch: string }
  targets: RunTarget[]
}

// --- Threshold search (POST /threshold) ---

export interface ThresholdRequest {
  command: string
  /** Dotted profile path, same shape as ParameterMetadata.field_path. */
  parameter: string
  low: number
  high: number
  trials?: number
  precision?: number
  profile?: EnvironmentProfile | null
  cwd?: string | null
  timeout?: number
  target?: string
}

/** search_points is list[dict] server-side, so every field is treated as optional. */
export interface ThresholdPoint {
  value?: number
  failure_rate?: number
  passed?: boolean
}

// Mirrors morph/schema/comparison.py's ThresholdResult.
export interface ThresholdResult {
  parameter: string
  safe_value: number
  failure_value: number
  boundary_estimate: number
  search_points: ThresholdPoint[]
}

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

// --- 2D Failure Surface, Differential Blame & Invariant Exporter ---

export interface SurfaceGridPoint {
  x: number
  y: number
  passed: boolean
  failure_rate: number
  runs: number
  exit_code?: number | null
  duration_ms?: number | null
  stdout?: string | null
  stderr?: string | null
}

export interface SafeBoundaryPoint {
  x: number
  y: number
  status: string
}

export interface BlameTrace {
  run_type: 'PASS' | 'FAIL'
  parameter_val: string
  file?: string | null
  line?: number | null
  function?: string | null
  operation?: string | null
  status_or_exception?: string | null
  duration_ms?: number | null
  summary_line: string
}

export interface DifferentialBlameResult {
  culpable_file?: string | null
  culpable_line?: number | null
  culpable_code?: string | null
  pass_trace?: BlameTrace | null
  fail_trace?: BlameTrace | null
  divergence_summary: string
  explanation: string
  suggested_fix?: string | null
}

export interface SurfaceResult {
  param_x: string
  param_y: string
  param_x_label: string
  param_y_label: string
  param_x_unit: string
  param_y_unit: string
  x_values: number[]
  y_values: number[]
  grid: SurfaceGridPoint[][]
  points: SurfaceGridPoint[]
  safe_boundary: SafeBoundaryPoint[]
  passing_count: number
  failing_count: number
  total_points: number
  highest_passing_point?: SurfaceGridPoint | null
  lowest_failing_point?: SurfaceGridPoint | null
  blame?: DifferentialBlameResult | null
  summary: string
}

export interface SurfaceRequest {
  project_path: string
  command?: string | null
  cwd?: string | null
  param_x?: string
  param_y?: string
  x_values?: number[] | null
  y_values?: number[] | null
  x_min?: number | null
  x_max?: number | null
  x_steps?: number | null
  y_min?: number | null
  y_max?: number | null
  y_steps?: number | null
  runs_per_point?: number
  adapter_name?: string
  supplied_profile?: EnvironmentProfile | null
}

export interface ExportInvariantRequest {
  project_name: string
  command?: string
  safe_latency_ms?: number
  safe_packet_loss?: number
  safe_cpu_quota?: number
  param_name?: string
  boundary_estimate?: number | null
  divergence_summary?: string | null
}

export interface ExportInvariantResponse {
  filename: string
  code: string
  summary: string
}
