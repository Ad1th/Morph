// Mirrors morph/schema/*.py. Kept in sync by hand; every optional backend
// field is optional here so a newer or older server never crashes the UI.

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
  language_tag?: ProfileField<string> | null
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

// --- runs (morph/schema/telemetry.py) ---

export interface TelemetryData {
  cpu_percent?: number | null
  memory_rss_mb?: number | null
  network_rx_bytes?: number | null
  network_tx_bytes?: number | null
  extra?: Record<string, unknown>
}

export interface FidelityEntry {
  status: string
  mechanism?: string
  detail?: string
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
  telemetry?: TelemetryData | null
  invalid?: boolean
  invalid_reason?: string | null
  command?: string | null
  seed?: number | null
  morph_version?: string | null
  host_fingerprint?: string | null
  profile_hash?: string | null
  adapter?: string | null
  fidelity?: Record<string, FidelityEntry>
}

// --- events (morph/schema/events.py) ---

export type EventKind =
  | 'phase_start'
  | 'condition_start'
  | 'trial'
  | 'condition_done'
  | 'comparison'
  | 'evidence'
  | 'search_probe'
  | 'verdict'
  | 'phase_done'

export interface TrialEvent {
  kind: EventKind
  condition: string
  phase: string
  trial_index?: number | null
  total?: number | null
  passed?: boolean | null
  duration_ms?: number | null
  failures_so_far?: number | null
  error_type?: string | null
  stdout_tail?: string | null
  stderr_tail?: string | null
  failures?: number | null
  failure_rate?: number | null
  p_value?: number | null
  is_significant?: boolean | null
  effect_label?: string | null
  classification?: string | null
  strongest_condition?: string | null
  e_value?: number | null
  evidence_threshold?: number | null
  pairs?: number | null
  decisive?: boolean | null
  param_value?: number | null
  safe_value?: number | null
  failure_value?: number | null
  boundary_estimate?: number | null
  extra?: Record<string, unknown>
}

// --- comparisons (morph/schema/comparison.py) ---

export type ComparisonMethod = 'fisher' | 'fisher_holm' | 'paired_e_value'

export interface TrialBatch {
  condition_label: string
  profile_overrides?: Record<string, unknown>
  total_runs: number
  failures: number
  failure_rate?: number
  run_results?: RunResult[]
}

export interface ComparisonResult {
  condition_label: string
  baseline_failures: number
  baseline_total: number
  treatment_failures: number
  treatment_total: number
  p_value?: number | null
  is_significant: boolean
  effect_label: string
  baseline?: TrialBatch | null
  treatment?: TrialBatch | null
  method?: ComparisonMethod
  alpha?: number
  p_value_decrease?: number | null
  p_value_adjusted?: number | null
  e_value?: number | null
  pairs?: number | null
  stopped_early?: boolean | null
  risk_difference?: number | null
  risk_difference_ci?: [number, number] | null
}

export type ThresholdOutcome = 'boundary_found' | 'never_fails' | 'always_fails' | 'inconclusive'

export interface ThresholdPoint {
  value?: number
  failure_rate?: number | null
  passed?: boolean | null
}

export interface ThresholdResult {
  parameter: string
  safe_value?: number | null
  failure_value?: number | null
  boundary_estimate?: number | null
  search_points: ThresholdPoint[]
  outcome?: ThresholdOutcome
  method?: 'bisection' | 'probabilistic_bisection'
  trials?: number | null
  credible_mass?: number | null
  credible_low?: number | null
  credible_high?: number | null
  probability_boundary_in_range?: number | null
  probability_never_fails?: number | null
  probability_always_fails?: number | null
  floor_failure_rate?: number | null
  ceiling_failure_rate?: number | null
  posterior?: { value: number; density: number }[]
  dose_response?: { value: number; failure_probability: number }[]
}

// --- experiments (morph/schema/experiment.py) ---

export type Classification =
  | 'environment_caused'
  | 'environment_exposed'
  | 'application_internal'
  | 'no_effect'
  | 'unknown'

export interface ExperimentResult {
  experiment_id?: string | null
  target_profile?: EnvironmentProfile | null
  baseline?: TrialBatch | null
  comparisons: ComparisonResult[]
  interactions?: ComparisonResult[]
  thresholds?: ThresholdResult[]
  classification: Classification | string
  strongest_condition: string
  summary: string
  warnings?: string[]
}

export type ExperimentMode = 'sequential' | 'batch'

export interface ExperimentStreamRequest {
  command: string
  target_profile: EnvironmentProfile
  cwd?: string | null
  trials?: number
  timeout_sec?: number
  mode?: ExperimentMode
  max_rounds?: number
  alpha?: number
}

// WebSocket frames from /ws/experiment/{id} and /ws/threshold/{id}.
export type JobFrame =
  | { type: 'connected'; experiment_id?: string; threshold_id?: string; status: string }
  | ({ type: 'event' } & TrialEvent)
  | { type: 'done'; result: ExperimentResult | ThresholdResult }
  | { type: 'error'; message: string; setup_error?: boolean; cancelled?: boolean }

// --- projects (morph/schema/project.py) ---

export interface ProjectInfo {
  project_id: string
  name: string
  path: string
  file_count: number
  entrypoints: string[]
  suggested_command?: string | null
  suggested_cwd?: string | null
  deps_failed: string[]
  source?: string
  repo?: string | null
  branch?: string | null
  commit?: string | null
  venv?: string | null
  created_at?: string | null
}

export interface GithubRepo {
  full_name: string
  name: string
  private: boolean
  default_branch: string
  description: string
  html_url: string
}

// --- platform ---

export interface RunTarget {
  id: string
  family: string
  label: string
  available: boolean
  reason?: string | null
  capabilities: Record<string, boolean>
}

export interface PlatformInfo {
  host: { family: string; version: string; arch: string }
  targets: RunTarget[]
}

// --- parameters (morph/schema/parameters.py) ---

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

// --- threshold requests ---

export type ThresholdMethod = 'bayes' | 'bisect'

export interface ThresholdRequest {
  command: string
  parameter: string
  low: number
  high: number
  method?: ThresholdMethod
  trials?: number
  max_trials?: number
  precision?: number | null
  credible_mass?: number
  profile?: EnvironmentProfile | null
  cwd?: string | null
  timeout?: number
  target?: string
}

// --- regressions (morph/schema/regression.py) ---

export interface RegressionArtifact {
  regression_id: string
  environment: EnvironmentProfile
  command: string
  expected_exit_code: number
  expected_max_failure_rate: number
  failure_signature?: string | null
  created_at?: string
  metadata: Record<string, unknown>
}

export interface ReplayResult {
  regression_id: string
  passed: boolean
  matches_expected: boolean
  failure_rate: number
  total_runs: number
  failures: number
  runs?: RunResult[]
  regression: RegressionArtifact
  summary: string
}

// --- profiles ---

export interface SavedProfileRef {
  id: string
  filename: string
  path: string
}

// --- export ---

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

// --- minimal failing set (POST /minimize) ---

export interface MinimizeResult {
  conditions: string[]
  minimal: string[]
  reproduced: boolean
  oracle_calls?: number
  history?: Record<string, unknown>[]
  summary: string
}
