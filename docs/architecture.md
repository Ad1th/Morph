# Morph: Software Architecture Document

> Build guide for developers. Read this, understand the system, then read the module docstrings, which are the source of truth for the maths.

This document describes every module, interface, data flow and file of Morph as it exists in the repository. It is derived from the [Morph PRD](./Morph_PRD.md); where the PRD and the code disagree, this document follows the code and says so. The statistical pipeline is explained in [how-it-works.md](./how-it-works.md); the demo corpus in [faultyapps.md](./faultyapps.md); cloud execution in [cloud.md](./cloud.md); project registration in [projects.md](./projects.md).

---

## 1. System Overview

Morph is a local-first developer tool that:

1. **Captures** environment conditions from a machine (OS, CPU, RAM, locale, timezone, filesystem, process limits, network).
2. **Reproduces** those conditions on another machine with OS-native controls, or a user-space proxy when it has no privileges.
3. **Runs** an application under the reproduced conditions and collects telemetry and provenance.
4. **Experiments**: paired sequential trials with anytime-valid evidence, or a fixed-N batch; a 2x2 interaction test; probabilistic bisection for thresholds; delta debugging for the minimal condition set.
5. **Classifies** the failure: environment-caused, environment-exposed, application-internal, or no effect.
6. **Exports** the discovered failure as a replayable regression bundle and a standalone CI test.

### Core loop

```
CAPTURE/DEFINE --> REPRODUCE --> RUN --> ISOLATE (sequential) --> INTERACTION --> THRESHOLD --> MINIMIZE --> CLASSIFY --> FIX --> REPLAY --> EXPORT
```

### High-level architecture

```
        CLI (Typer)        TUI (Textual)        Dashboard (React/Vite)
             |                   |                        |
             +-------------------+------------------------+
                                 |
                       API service layer (morph/api/service.py)
                                 |
              +------------------+------------------+
              |                  |                  |
          Profiler        Runtime controller    Experiment engine
              |                  |                  |
              |            OS adapter              |
              |      +-----------+-----------+      |
              |    Linux       macOS      Windows   |
              |      \           |           /      |
              |       +-- ProxyAdapter (no root) ---+
              |                  |
              |           Target process  <--- telemetry collector (rlimits, kill tree, provenance)
              |
        EnvironmentProfile JSON  <---  cloud worker over SSH (same `morph run`)
```

---

## 2. Module Inventory

| Module | Directory | Responsibility |
|---|---|---|
| CLI | `morph/cli/main.py` | Typer app: `connect`, `reinstall`, `projects`, `capture`, `define`, `run`, `experiment`, `demo`, `threshold`, `minimize`, `cloud`, `save`, `replay`, `export`, `serve`, `tui`, `doctor` |
| TUI | `morph/tui/` | Textual console: `app.py`, `orchestrator.py` (engine bridge), `screens/`, `widgets/`, `demo.py` (recorded replay), `profiles.py`, `perf.py` |
| API server | `morph/api/app.py`, `routes/`, `service.py`, `defaults.py`, `validation.py` | FastAPI; every route mounted at `/api/v1` and at the root; shared defaults with the CLI |
| Profiler | `morph/profiler/capture.py`, `collectors/{cpu,memory,os_info,locale_info,network,filesystem,process_limits}.py` | Captures the host into an `EnvironmentProfile` |
| Runtime | `morph/runtime/controller.py`, `runner.py`, `state.py` | Applies a profile through an adapter, runs the command, guarantees cleanup; crash-safe record of native side effects |
| OS adapters | `morph/runtime/adapters/{base,linux,macos,windows,proxy}.py` | Native shaping when privileged, `ProxyAdapter` otherwise; per-field fidelity |
| Experiment engine | `morph/engine/` | `sequential.py`, `anytime.py`, `experiment.py`, `comparison.py`, `classifier.py`, `threshold.py`, `boundary.py`, `minimize.py`, `runners.py`, `progress.py`, `errors.py`, `validator.py`, `surface.py`, `blame.py`, `exporter.py` |
| Telemetry | `morph/telemetry/collector.py`, `parser.py`, `provenance.py` | Subprocess launch, rlimits, output capture, error extraction, seed/version/host fingerprint |
| Regression | `morph/regression/artifact.py`, `replay.py`, `exporter.py` | Save, load, replay `.morph` bundles; generate `test_morph_invariant.py` |
| Cloud | `morph/cloud/capability.py`, `worker.py`, `dispatch.py` | Local capability check, SSH worker, explicit `--cloud` routing |
| Projects | `morph/projects.py`, `project_setup.py`, `github.py`, `runenv.py` | Registry under `~/.morph`, clones, per-project venvs, GitHub auth |
| Config | `morph/config.py`, `schema/config.py`, `morph.yaml` | `morph.yaml` discovery (stops at the git root or `$HOME`), `cloud:` block |
| Environment helper | `morph/environment.py` | `morph.environment()` context manager used by exported invariant tests |
| Schema | `morph/schema/` | Pydantic models: `profile`, `telemetry`, `trials`, `experiment`, `comparison`, `events`, `regression`, `parameters`, `project`, `surface`, `blame`, `config` |
| Demo corpus | `apps/` | Six deliberately faulty apps, shared `conftest.py`, `netshape.py` hand-off |
| Demo profiles | `profiles/` | One `EnvironmentProfile` per demo condition |
| Frontend | `frontend/` | React + TypeScript + Vite dashboard |
| Tests | `tests/` | pytest suite for `morph/`; `apps/*/test_app.py` for the corpus |

---

## 3. Directory Structure

```
morph/
  __init__.py
  config.py                      # morph.yaml discovery and loading
  environment.py                 # morph.environment(latency_ms=..., packet_loss=...) for exported tests
  github.py                      # token resolution, device flow, repo listing
  projects.py                    # project registry (~/.morph/projects)
  project_setup.py               # clone + per-project venv / npm install
  runenv.py                      # interpreter / venv resolution for a project command

  cli/
    main.py                      # the Typer app (see section 7)

  api/
    app.py                       # FastAPI factory: CORS, /health, /version, routers at /api/v1 and /
    service.py                   # shared orchestration used by CLI and routes (experiment, threshold, minimize, doctor)
    defaults.py                  # TRIALS, SEQUENTIAL_MAX_ROUNDS, ALPHA, THRESHOLD_*, DEMO_*, SERVE_*
    validation.py
    routes/
      profiles.py                # capture, save/list/get/delete, reconcile
      parameters.py              # parameter metadata for the UI
      runs.py                    # one run under a profile
      experiments.py             # blocking, streaming, list/get/delete
      threshold.py               # blocking and streaming
      minimize.py                # ddmin over deviating conditions
      surface.py                 # 2D failure surface, differential blame, invariant export
      regressions.py             # list/save/get/replay/delete
      projects.py                # upload/local/github connect, install, get/put/delete, GitHub auth
      platform.py                # host OS and run targets
      ws.py                      # /ws/experiment/{id}, /ws/threshold/{id}

  schema/
    profile.py                   # EnvironmentProfile, ProfileField, FieldStatus
    telemetry.py                 # RunResult (invalid, provenance, fidelity), TelemetryData
    trials.py                    # TrialBatch
    experiment.py                # ExperimentConfig, ExperimentResult
    comparison.py                # ComparisonResult, ThresholdResult, SearchPoint
    events.py                    # TrialEvent (the live event stream)
    regression.py                # RegressionArtifact, ReplayResult
    parameters.py                # ParameterMetadata
    project.py                   # ProjectInfo
    surface.py, blame.py         # SurfaceRequest/Result, DifferentialBlameResult
    config.py                    # MorphConfig, AdaptersConfig, CloudConfig

  profiler/
    capture.py                   # capture_environment()
    collectors/
      cpu.py, memory.py, os_info.py, locale_info.py, network.py, filesystem.py, process_limits.py

  runtime/
    controller.py                # RuntimeController: apply -> run -> cleanup; reconcile_profile_statuses
    runner.py                    # execute_command(): os.environ + overrides -> collector
    state.py                     # ~/.morph/state/shaping.json: tc/dnctl/cgroup entries with undo commands
    adapters/
      base.py                    # BaseAdapter, Fidelity, ProxyAdapter, locale/timezone helpers, plan_proxy_path
      linux.py                   # tc netem on lo, cgroup cpu.max / memory.max (root or MORPH_CGROUP_PATH)
      macos.py                   # dummynet pipe + pf anchor when root; proxy fallback; CPU/RAM hints only
      windows.py                 # proxy fallback; CPU/RAM hints only
      proxy.py                   # ProxyServer: RTT delay line, RTO-stall loss model, bandwidth bucket, seed

  engine/
    sequential.py                # run_sequential_experiment: paired round-robin, early stopping
    anytime.py                   # PairedEvidence: Beta-mixture e-process, anytime p, Bonferroni bar
    experiment.py                # run_trials, isolate_variables, detect_interaction, run_experiment (batch)
    comparison.py                # one-sided Fisher, Wilson, Newcombe CI, Holm
    classifier.py                # four-way classification
    threshold.py                 # search_threshold: deterministic bisection
    boundary.py                  # locate_boundary: probabilistic bisection, credible interval
    minimize.py                  # ddmin, batch_oracle
    runners.py                   # profile -> run_fn / run_at builders shared by CLI and API
    progress.py                  # OnEvent, emit, coerce_result, run_valid_trial (invalid-trial retry)
    errors.py                    # InvalidTrialError
    validator.py                 # profile validation against parameter metadata
    surface.py                   # 2D grid (latency x loss) with safe/failing contour
    blame.py                     # differential blame: diff pass vs fail traces
    exporter.py                  # generate_invariant_test_code

  telemetry/
    collector.py                 # run_with_telemetry: shell=False, interpreter pinning, session kill, rlimits, invalid exit codes
    parser.py                    # extract_error_type / message / stack_trace
    provenance.py                # morph_version, host_fingerprint, seed_from_env

  regression/
    artifact.py                  # save / load .morph bundles
    replay.py                    # replay_regression -> ReplayResult
    exporter.py                  # export_ci_test

  cloud/
    capability.py                # assess_locally -> HostCapability (shortfalls)
    worker.py                    # RemoteWorker: ssh argv, probe, run
    dispatch.py                  # run_anywhere, NotReproducibleAnywhere

  tui/
    app.py, app.tcss, messages.py, orchestrator.py, demo.py, profiles.py, perf.py
    screens/  home, environment, experiment, monitor, threshold, projects, regressions
    widgets/  condition_lane, interaction_matrix, profile_diff, slider, threshold_gauge, verdict_card

apps/                            # see docs/faultyapps.md
  conftest.py, netshape.py, requirements.txt, README.md
  timeout/  pool_retry/  race/  locale_parse/  fd_limit/  tz_dst/
    __init__.py  __main__.py  app.py  test_app.py  README.md

profiles/                        # flagship.json, high_latency.json, locale_de.json, tz_dst.json, fd_limit.json, race_yield.json

frontend/                        # React + TypeScript + Vite
  src/  App.tsx  main.tsx  api/  components/  screens/  theme/

scripts/
  setup_gcp_worker.sh            # bootstrap an SSH worker: packages, venv, sudo tc, delegated cgroup, shaping self-check

tests/                           # 28 modules; see section 15
morph.yaml                       # project config (section 13)
pyproject.toml                   # package config, pytest markers (slow, needs_linux, needs_root), ruff
```

Runtime state lives under `~/.morph/`: `projects/`, `checkouts/`, `venvs/`, `state/shaping.json`; regression bundles under `.morph/regressions/` in the working directory.

---

## 4. Data Models (Schema)

### 4.1 Environment profile (`schema/profile.py`)

Every field is a `ProfileField {value, status}`. `FieldStatus` is `captured`, `requested`, `reproduced`, `approximated`, `unavailable`.

```python
class OSInfo:         family, version, kernel_version?
class CPUInfo:        architecture, cores, logical_processors, clock_mhz?, quota_percent?
class MemoryInfo:     total_mb, swap_mb?, pressure_percent?
class LocaleInfo:     locale, timezone, language_tag?
class FilesystemInfo: case_sensitive, filesystem_type?, read_only?, disk_space_limit_mb?, disk_read_latency_ms?, disk_write_latency_ms?
class NetworkInfo:    latency_ms (an RTT), packet_loss_percent, bandwidth_mbps?, jitter_ms?, available?, connection_type?
class ProcessInfo:    timeout_s?, max_processes?, thread_limit?, fd_limit?

class EnvironmentProfile:
    version = "1.0"; os; cpu; memory; locale; filesystem?; network?; process?; env_vars: dict[str, str] = {}
```

`network.latency_ms` is a **round-trip** time everywhere (profile, proxy, native adapters, threshold results). `env_vars` are exported verbatim to the child and override the adapter's own exports. `jitter_ms` is carried by the schema and supported by the proxy but not yet passed through the controller.

### 4.2 Run result (`schema/telemetry.py`)

```python
class RunResult:
    run_id, exit_code, stdout, stderr, duration_ms, peak_memory_mb?, passed  # passed == (exit_code == 0)
    error_type?, error_message?, timestamp, telemetry: TelemetryData
    # invalid-trial convention
    invalid: bool = False           # exit 2, 126, 127, or the command could not launch
    invalid_reason: str | None
    # provenance
    command, seed?, morph_version, host_fingerprint, profile_hash?, adapter?, fidelity: dict[str, Fidelity]
```

`fidelity` maps a profile path (`network.latency_ms`, `cpu.quota_percent`, ...) to `{status, mechanism, detail}`: what the adapter actually did.

### 4.3 Trials and comparisons (`schema/trials.py`, `schema/comparison.py`)

```python
class TrialBatch:        condition_label, total_runs, failures, failure_rate, run_results

class ComparisonResult:  condition_label, baseline_failures/total, treatment_failures/total,
                         p_value, is_significant, effect_label ("no_effect" | "significant_increase" | "significant_decrease"),
                         method ("fisher" | "fisher_holm" | "paired_e_value"), alpha,
                         p_value_decrease?, p_value_adjusted?, e_value?, pairs?, stopped_early?,
                         risk_difference?, risk_difference_ci?

class ThresholdResult:   parameter, safe_value?, failure_value?, boundary_estimate?, search_points,
                         outcome ("boundary_found" | "never_fails" | "always_fails" | "inconclusive"),
                         method ("bisection" | "probabilistic_bisection"), trials?,
                         credible_mass?, credible_low?, credible_high?,
                         probability_boundary_in_range?, probability_never_fails?, probability_always_fails?,
                         floor_failure_rate?, ceiling_failure_rate?, posterior[], dose_response[]
```

### 4.4 Experiment (`schema/experiment.py`)

```python
class ExperimentConfig:  command, target_profile?, trials, timeout_sec, cwd?, mode ("sequential" | "batch"), max_rounds, alpha
class ExperimentResult:  experiment_id?, target_profile?, baseline: TrialBatch, comparisons, classification, strongest_condition, summary
```

`classification` is one of `environment_caused`, `environment_exposed`, `application_internal`, `no_effect`.

### 4.5 Events (`schema/events.py`)

`TrialEvent.kind` is `phase_start`, `condition_start`, `trial`, `condition_done`, `comparison`, `evidence`, `search_probe`, `verdict`, `phase_done`. A `trial` event never carries a p-value; `evidence` carries the anytime-valid `e_value`, `evidence_threshold`, `pairs`, `decisive`; `search_probe` carries `param_value`, `safe_value`, `failure_value`, `boundary_estimate`. Invalid trials appear as `trial` events with `passed=None` and `extra={"invalid": True, "reason": ...}`.

### 4.6 Regression artifact (`schema/regression.py`)

```python
class RegressionArtifact: regression_id, environment: EnvironmentProfile, command, expected_exit_code,
                          expected_max_failure_rate, failure_signature?, created_at, metadata
class ReplayResult:       regression_id, total_runs, failures, failure_rate, matches_expected
```

---

## 5. Module Deep Dives

### 5.1 Profiler (`morph/profiler/`)

`capture_environment()` runs every collector and returns a profile with every field `captured`. `network` is `None` in a capture (nothing measures the host's own path); `runners.with_unconstrained_network` fills it as 0 ms / 0 % when a search needs it. `process_limits.py` reads the soft `RLIMIT_NOFILE` / `RLIMIT_NPROC`, which is how a captured profile can carry a `fd_limit`.

### 5.2 Runtime controller and adapters (`morph/runtime/`)

```
controller.run(profile, command, timeout, cwd)
    |
    +--> adapter.apply_network(latency_ms, packet_loss_percent, bandwidth_mbps)   # profile.network; available=False => loss 100 %
    +--> adapter.apply_cpu(max_cores, quota_percent)
    +--> adapter.apply_memory(limit_mb)
    +--> adapter.apply_locale(locale_str, timezone)                              # LC_ALL, LANG, TZ
    +--> env = adapter.get_env_overrides() | profile.env_vars
    +--> execute_command(command, env_overrides=env, timeout, cwd,
                         max_processes=profile.process.max_processes, fd_limit=profile.process.fd_limit)
    +--> finally: adapter.cleanup()
```

`get_default_adapter()` picks `LinuxAdapter`, `MacOSAdapter` or `WindowsAdapter` by `platform.system()`; `force_proxy=True` picks `ProxyAdapter` directly. `reconcile_profile_statuses()` marks each field `reproduced` / `approximated` / `unavailable` from the adapter's `capabilities()` before a run; the adapter's `plan(profile)` and post-run `fidelity()` report the mechanism per field.

| Condition | Linux | macOS | Windows |
|---|---|---|---|
| Network shaping | `tc qdisc netem` on `lo` (root or `sudo -n`); else proxy | dummynet pipe + `pf` anchor `morph` (root); else proxy | proxy |
| CPU quota / cores | cgroup v2 `cpu.max` (root, or a delegated `MORPH_CGROUP_PATH`); else `MORPH_CPU_QUOTA_PERCENT` hint, `unavailable` | hint only, `unavailable` | hint only, `unavailable` |
| Memory limit | cgroup v2 `memory.max` (same conditions); else hint | hint only, `unavailable` | hint only, `unavailable` |
| Locale / timezone | `LC_ALL`, `LANG`, `TZ` | same | same (the CRT ignores `LC_ALL`; the corpus apps read it themselves) |
| Process limits | `setrlimit` in the child | same | ignored |

Native delays are per direction, so the adapters apply `latency_ms / 2`. Every native change is recorded in `~/.morph/state/shaping.json` **before** it is applied (`runtime/state.py`), with the undo command; `morph doctor` finds and undoes what a killed process left behind.

**The proxy hand-off contract (`ProxyAdapter`, `adapters/proxy.py`).** Without privileges the adapter cannot intercept anything. It starts a `ProxyServer` and exports:

```
MORPH_NET_LATENCY_MS         RTT to inject
MORPH_NET_PACKET_LOSS_PCT    per-chunk loss probability
MORPH_NET_BANDWIDTH_KBPS     optional token-bucket cap
MORPH_SEED                   reproducible loss pattern
MORPH_PROXY_HOST/PORT, MORPH_UPSTREAM_PORT   the adapter's own listener (for targets with an external upstream)
```

A target that hosts its own localhost server (every app under `apps/`) reads `MORPH_NET_*` and fronts its server with the same `ProxyServer` class in-process (`apps/netshape.py`). `ProxyServer` semantics: `latency_ms` is an RTT, half per direction, chunks pipelined; a lost chunk is delivered late after `max(200 ms, 3 x RTT)`, doubling on consecutive losses, in order, never corrupted; after `max_retransmits` (6) consecutive losses the connection is reset (`ECONNRESET`), which is how "offline" surfaces; `bandwidth_kbps` is a shared token bucket; `jitter_ms` is Gaussian extra delay. The proxy is the default path on a developer laptop and on CI.

### 5.3 Experiment engine (`morph/engine/`)

Engine functions take `run_fn` callbacks (returning `bool` or `RunResult`) and an optional `on_event`, so they are testable without a target. `runners.py` builds the callbacks from a profile and a command: `build_baseline_and_candidates` yields `latency_only`, `loss_only` and `full_treatment` (`full_target` in the CLI) for a profile that requests both network fields.

| Mode | Function | What it does |
|---|---|---|
| Sequential isolation (default) | `sequential.run_sequential_experiment` | Paired round-robin trials; per-candidate `PairedEvidence` e-process (`anytime.py`); stop at `E >= K/alpha`; min 3 rounds, max 12 by default |
| Batch isolation | `experiment.run_experiment` | N trials per condition; one-sided Fisher (`comparison.py`) with Holm across candidates; Newcombe CI |
| Interaction | `experiment.detect_interaction` | The 2x2: `neither`, A, B, A+B; `interaction_confirmed` when only A+B is significant |
| Threshold, Bayesian (default) | `boundary.locate_boundary` | Probabilistic bisection; logistic dose-response with floor/ceiling nuisance grid; credible interval; `never_fails` / `always_fails` guards |
| Threshold, bisection | `threshold.search_threshold` | Deterministic halving, majority vote per probe |
| Minimal set | `minimize.ddmin` | Delta debugging over deviating conditions; `batch_oracle` for flaky targets |
| Classification | `classifier.classify_failure` | Four-way, Wilson lower bound for "internally flaky" |
| Surface | `surface.py` | Latency x loss grid with safe / failing contour |
| Blame | `blame.py` | Diff of passing vs failing traces (file, line, exception, duration) |
| Invariant export | `exporter.py` | `test_morph_invariant.py` code generation |

Invalid trials: `progress.run_valid_trial` retries a `RunResult.invalid` result up to `INVALID_TRIAL_ATTEMPTS` times and raises `InvalidTrialError` if every attempt is invalid, so a setup problem is reported as such, never as a verdict.

The maths, with references, is in [how-it-works.md](./how-it-works.md).

### 5.4 Telemetry collector (`morph/telemetry/`)

`run_with_telemetry(command, env, timeout, cwd, max_processes, fd_limit)`:

- **`shell=False`.** POSIX: `shlex.split`, a bare `python`/`python3`/`python3.x` first token is pinned to `sys.executable`; the child starts in its own session (`start_new_session=True`). Windows: the command line is passed through untouched (only the leading bare `python` rewritten), `CREATE_NEW_PROCESS_GROUP`.
- **Resource limits.** A `preexec_fn` applies `RLIMIT_NPROC` / `RLIMIT_NOFILE` (clamped to the host's hard limits, with a note) and joins `MORPH_CGROUP_PATH` when set. Installed only when something was requested.
- **Timeout.** `communicate(timeout)`; on expiry the whole process group is signalled (SIGTERM, grace, SIGKILL) plus a psutil sweep for anything that left the group; `taskkill /T` on Windows. `error_type = "TimeoutExpired"`, exit code -1.
- **Output.** stdout/stderr bounded to 2 MiB each, tail kept; `error_type` / `error_message` / `stack_trace` extracted from stderr by `parser.py`.
- **Invalid.** Exit 2, 126, 127 and launch failures (`FileNotFoundError` -> 127, `PermissionError` -> 126) set `invalid=True` with a reason.
- **Provenance.** `seed`, `morph_version`, `host_fingerprint`, `profile_hash`, `adapter`, `fidelity` (from `provenance.py` and the controller).
- **Monitoring.** Peak RSS and CPU sampled at 10 Hz (not faster: enumerating the process table at 50 Hz perturbed the timing-sensitive runs Morph measures).

### 5.5 Regression artifacts (`morph/regression/`)

```
.morph/regressions/<id>/
  environment.json     # the EnvironmentProfile that triggers the failure
  command.json         # {"command": ..., "timeout": ...}
  expected.json        # {"exit_code": 0, "max_failure_rate": ...}
  metadata.json        # created_at, failure_signature, provenance
```

`morph save` writes one; `morph replay <path|id> -n N` runs it and reports `COMPLIANT` / `VIOLATION`; `morph export <path|id> -o test_morph_invariant.py` writes a standalone pytest file that uses `morph.environment()` to apply the proxy conditions and asserts the safe envelope.

---

## 6. API Contract (`morph/api/`)

Every route is mounted twice: under `/api/v1` and at the root (for existing clients). CLI and routes share `morph/api/defaults.py` and `morph/api/service.py`, so the same request means the same experiment however it arrives.

| Method | Path | Body | Response | Purpose |
|---|---|---|---|---|
| `GET` | `/health`, `/version` | none | status / versions | Liveness, Morph and runtime versions |
| `POST` | `/profiles/capture` | none | `EnvironmentProfile` | Capture this machine |
| `POST` / `GET` | `/profiles` | profile / none | `{"id"}` / list | Save, list saved profiles |
| `GET` / `DELETE` | `/profiles/{id}` | none | profile / `{}` | Get, delete |
| `POST` | `/profiles/reconcile` | profile | profile with statuses | What this host can reproduce |
| `GET` | `/parameters` | none | `dict[str, ParameterMetadata]` | Control metadata for the UI |
| `GET` | `/platform` | none | `PlatformInfo` | Host OS and run targets |
| `POST` | `/run` | `{command, profile?, timeout?, cwd?}` | `RunResult` | One run under a profile (inline, not by id) |
| `POST` | `/experiments` | `ExperimentConfig` | `ExperimentResult` | Blocking experiment (sequential or batch) |
| `POST` | `/experiments/stream` | `ExperimentConfig` | `{experiment_id, status}` | Start in the background; events over WebSocket |
| `GET` / `DELETE` | `/experiments`, `/experiments/{id}` | none | list / result | Cached results (50 max) |
| `POST` | `/threshold`, `/threshold/stream` | `ThresholdRequest` (`method`, `max_trials`, `precision`, ...) | `ThresholdResult` / id | Threshold search |
| `POST` | `/minimize` | `{command, profile, conditions?, runs, fail_rate}` | `MinimizeResult` | ddmin minimal condition set |
| `POST` | `/surface`, `/blame`, `/export/invariant` | `SurfaceRequest` / ... | `SurfaceResult` / `DifferentialBlameResult` / file | 2D failure surface, differential blame, CI test |
| `GET` / `POST` | `/regressions` | none / `{profile, command, ...}` | list / `{id}` | List, save |
| `GET` / `DELETE` | `/regressions/{id}` | none | artifact / `{}` | Get, delete |
| `POST` | `/regressions/{id}/replay` | `{trials?}` | `ReplayResult` | Replay |
| `POST` | `/projects/upload`, `/projects/local`, `/projects/github` | ... | `ProjectInfo` | Connect a project |
| `GET` / `PUT` / `DELETE` | `/projects`, `/projects/{id}` | ... | list / `ProjectInfo` | Registry |
| `POST` | `/projects/{id}/install` | none | `ProjectInfo` | Build the per-project venv |
| `GET` / `POST` | `/projects/github/auth-status`, `/github/device-code`, `/github/poll-token`, `/github/repos` | ... | ... | GitHub auth and repo listing |

### WebSocket

| Path | Payload | Purpose |
|---|---|---|
| `/ws/experiment/{id}` | `{"type": "event", ...TrialEvent}` then `{"type": "done", "result"}` or `{"type": "error"}` | Live experiment |
| `/ws/threshold/{id}` | same shape with `search_probe` events | Live threshold search |

---

## 7. CLI Interface (`morph/cli/main.py`)

```bash
# projects
morph connect owner/repo [--branch b] [--install] [--name n]     # or a URL or a local path
morph projects [--rm id]
morph reinstall <id|name>

# environments
morph capture [-o profile.json] [--json]
morph define [-t default|high-latency|constrained] [--latency ms] [--loss pct] -o target.json

# run and experiment
morph run -c "<cmd>" [-p profile.json] [--cwd d] [--timeout s] [--force-proxy] [--cloud] [--json]
morph experiment -c "<cmd>" [-p profile.json] [--mode sequential|batch] [-n trials] [--max-rounds r] [--alpha a] [--latency ms] [--loss pct] [--json]
morph demo [--max-rounds r] [--latency 120] [--loss 18]          # apps/pool_retry, sequential 2x2
morph threshold -c "<cmd>" --parameter network.latency_ms --low 0 --high 500 [--method bayes|bisect] [-n trials] [--max-trials t] [--precision p]
morph minimize -c "<cmd>" -p profile.json [--condition f ...] [-n runs] [--fail-rate r]
morph cloud [-p profile.json]                                     # capability check + worker probe

# regressions
morph save --id <id> -p profile.json -c "<cmd>" [--expected-exit 0] [--max-failure-rate r]
morph replay <path|id> [-n trials]
morph export <path|id> [-o test_morph_invariant.py]

# interfaces and health
morph serve [--host h] [--port 8000] [--reload] [--origin o]
morph tui [--demo]
morph doctor [--no-network] [--json]
```

`--project <id>` on `run`, `experiment`, `threshold` and `minimize` fills the command and working directory from the registry. Diagnostics go to stderr; `--json` keeps stdout machine-readable. Exit codes: 0 ok, 1 failure/violation, 2 not reproducible / usage.

---

## 8. Frontend and TUI

**Dashboard** (`frontend/`, React + TypeScript + Vite): talks to the API at `/api/v1`, subscribes to `/ws/experiment/{id}` for live trials; screens for environment configuration, preparing, experiment, verdict, threshold and surface. The UI contract is in [ui-spec.md](./ui-spec.md).

**TUI** (`morph tui`, Textual): `orchestrator.py` builds `RunResult`-returning runners and drives the engine with an `on_event` callback inside a thread worker; `EXPERIMENT_MODES = ("sequential", "batch")`, `THRESHOLD_METHODS = ("bayesian", "bisection")`. Screens: home, environment, experiment, monitor, threshold, projects, regressions. Widgets: condition lanes (one per candidate, with the live e-value), interaction matrix, profile diff, sliders, threshold gauge, verdict card. `morph tui --demo` replays a recorded experiment with no target app or network.

---

## 9. Data Flow: End-to-End Walkthrough

The flagship, as measured (see `apps/pool_retry/README.md`):

```
1. profile      profiles/flagship.json: network.latency_ms 120 (RTT), packet_loss_percent 18, both `requested`
2. reproduce    MacOSAdapter (no root) -> ProxyAdapter -> exports MORPH_NET_LATENCY_MS=120, MORPH_NET_PACKET_LOSS_PCT=18, MORPH_SEED
3. run          collector launches `python -m apps.pool_retry test` (pinned interpreter, own session)
                app fronts its server with ProxyServer; 16 requests through a 2-slot pool; deadline 2.8 s
                -> exit 1, stdout {"result":"fail","signal":"DeadlineExceeded",...}, RunResult.fidelity network.*=reproduced (proxy)
4. isolate      morph experiment (sequential, 12 rounds max)
                round k: baseline, then latency_only / loss_only / full_target in rotating order; e-value per candidate
                baseline 0/12, latency_only 0/12, loss_only 0/12, full_target 9/9: E = 102 after 9 pairs, stopped early, anytime p = 0.0098
5. classify     baseline never failed, full_target significantly worse -> environment_caused; strongest: full_target
6. interaction  detect_interaction: A alone no_effect, B alone no_effect, A+B significant -> interaction_confirmed
7. threshold    locate_boundary on network.latency_ms with loss held at 18 %: credible interval around the flip
8. minimize     ddmin over {latency_ms, packet_loss_percent, ...} -> {latency_ms, packet_loss_percent}
9. fix          --fixed (pool sized to the batch); the same experiment: every leg 0/12, no_effect
10. regression  morph save; morph replay -> COMPLIANT; morph export -> test_morph_invariant.py
```

---

## 10. Environment Comparison Logic

`reconcile_profile_statuses(profile, adapter)`: OS family equal -> `reproduced` (version `approximated`), else `unavailable`; CPU cores `approximated` when the adapter claims `cpu`, architecture `reproduced` only when it matches `platform.machine()`; memory `approximated` or `unavailable`; locale and timezone `reproduced` when the adapter claims `locale`; network `reproduced` (bandwidth `approximated`) when it claims `network`. After the run, `RunResult.fidelity` records what actually happened per field, which is what the UI should show.

`cloud.capability.assess_locally(profile)` decides whether **another machine** is needed: more RAM (2 % tolerance), more cores, a different architecture, or a different OS family. Locale, timezone, limits and shaping are never shortfalls.

---

## 11. Demo Failure Corpus

Six apps under `apps/`, each with a one-line fix behind `--fixed`, a two-tier self-test and a profile under `profiles/`. Numbers are failures / trials on macOS through Morph's own paths.

| App | Knob | Baseline | Under condition | Classification |
|---|---|---|---|---|
| A `timeout` | `network.latency_ms` (RTT) | 0/20 | 20/20 at 120 ms; flips at ~42 ms | environment-caused |
| B `pool_retry` (flagship) | latency **and** loss | 0/20 | 19/20 at 120 ms / 18 %; each alone 0/20 | environment-caused, interaction |
| C `race` | `cpu.quota_percent` (Linux root) or `env_vars.MORPH_C_YIELD_EVERY` | 0/10 | 10/10 | environment-exposed |
| D `locale_parse` | `locale.locale` = de_DE (comma decimal) | 0/5 | 5/5 | environment-caused |
| E `fd_limit` | `process.fd_limit` = 64 | 0/10 | 10/10; flips between 96 and 112 | environment-caused |
| F `tz_dst` | `locale.timezone` = America/Sao_Paulo | 0/5 | 5/5 | environment-caused |

Signals: `TimeoutException`, `DeadlineExceeded`, `RaceDetected`, `LocaleParseMismatch`, `EMFILE`, `ScheduleDrift`. Details, mechanisms and the verification protocol: [faultyapps.md](./faultyapps.md).

---

## 12. Cloud Fallback Architecture

```
morph run --cloud -p profile.json -c "<cmd>"
      |
  assess_locally(profile)
      |
  reproducible here?  --yes-->  local RuntimeController.run
      |
      no
      |
  worker configured (morph.yaml cloud: / MORPH_CLOUD_*)?  --no-->  NotReproducibleAnywhere (exit 2)
      |
      yes
      |
  ssh worker 'morph run --profile <stdin> --command ... --json'  -->  RunResult (with the worker's provenance)
```

Transport is SSH to any Linux box (GCP instance, Raspberry Pi); there is no second execution engine and no provider API. Dispatch is **explicit**: without `--cloud`, a configured worker never changes a local run. Details and worker setup: [cloud.md](./cloud.md).

---

## 13. Configuration

`morph.yaml` is found by walking up from the working directory, stopping at a git root or `$HOME`; a malformed file warns and falls back to defaults.

```yaml
version: "1.0"
default_trials: 5
significance_level: 0.05
proxy_port: 9876              # ProxyAdapter's own listener; targets that host their own server use MORPH_NET_* instead

adapters:
  network: proxy              # "proxy" | "native"
  cpu: native
  memory: native
  locale: native

cloud:
  provider: ssh               # provenance only: ssh | gcp | pi
  host: ""                    # keep blank in git; MORPH_CLOUD_HOST wins
  user: ""                    # MORPH_CLOUD_USER
  python: ~/morph/.venv/bin/python
  workdir: ~/morph
```

Environment: `MORPH_CLOUD_HOST` / `MORPH_CLOUD_USER` / `MORPH_CLOUD_SSH_KEY` (aliases `MORPH_WORKER_*`), `MORPH_NO_NETWORK=1` (no SSH ever), `MORPH_SEED` (reproducible loss), `MORPH_CGROUP_PATH` (delegated cgroup for quota/memory without root), `MORPH_GITHUB_TOKEN` / `GITHUB_TOKEN` / `GH_TOKEN`.

---

## 14. Error Handling Rules

As implemented today; intent is noted where the code still falls short.

1. **Adapter failures fall back, and say so.** A native shaping command that fails is undone and recorded; the adapter falls back to the proxy and reports the mechanism in `fidelity`. Conditions with no mechanism on this host (CPU/RAM on macOS) are `unavailable` with an env hint, never claimed as applied.
2. **Subprocess timeouts.** Default 30 s, `profile.process.timeout_s` overrides. The whole process tree is killed. A timeout counts as a failure (`TimeoutExpired`, exit -1).
3. **Invalid trials are not evidence.** Exit 2 / 126 / 127 / launch failure -> `invalid`; the engine retries a few times, then raises `InvalidTrialError` rather than reporting a verdict.
4. **Partial reproduction is visible.** `reconcile_profile_statuses` before, `fidelity` after: a run never claims full reproduction when a condition was skipped.
5. **Native side effects survive crashes.** `runtime/state.py` records every `tc` / dummynet / cgroup change with its undo command before applying it; `morph doctor` cleans up. Intent not yet implemented: a proxy that dies mid-batch does not automatically invalidate and re-queue that batch's trials.
6. **Statistics stay honest under live viewing.** Only anytime-valid quantities (e-values, credible intervals, Wilson bounds) are streamed; Fisher p-values are computed once, at the end, and labelled.

---

## 15. Testing Strategy

| Tier | Scope | Command | When |
|---|---|---|---|
| Unit + integration (`tests/`, 28 modules) | schema, comparison maths, anytime e-process, boundary posterior, sequential engine, threshold, classifier, adapters, proxy, collector, runner, controller, regression, API routes, WebSocket stream, projects, cloud (SSH mocked, `MORPH_NO_NETWORK`), TUI, e2e | `pytest -q --timeout=120` | every push and PR, blocking |
| Corpus contract tier (`apps/`) | baseline passes, condition fails, exit codes, JSON line, clean stderr; ~10 s | `pytest apps -m "not slow"` | every push and PR, blocking (`sudo locale-gen de_DE.UTF-8` first; Linux/root-only tests skip themselves) |
| Corpus statistical tier | acceptance rates over 10 to 20 trials with binomial-aware bounds | `pytest apps -m slow` | every push and PR, advisory (`continue-on-error`) |
| Lint | `ruff check morph/ tests/ apps/` | | blocking |
| CLI smoke, proxy self-check | `morph --help`, `morph capture`, `morph run`, `python -m morph.runtime.adapters.proxy` | | blocking |
| Frontend smoke | dashboard loads against a running `morph serve` | manual / Playwright | pre-review |
| End to end on hardware | `tc netem` on the Pi vs the proxy; `apps/race` under a real cgroup quota | manual | pre-demo |

Markers `slow`, `needs_linux`, `needs_root` are registered in `pyproject.toml` with `--strict-markers`; `apps/conftest.py` turns the platform markers into skips.

---

## 16. Security and Privacy

- The profiler captures application-relevant conditions only: no browser history, documents or credentials. `env_vars` in a profile are the ones a developer typed, not a dump of `os.environ`.
- Targets run with `shell=False`; a command string is tokenised, never handed to a shell.
- The proxy relays only connections made to its own port (or the in-app proxy an app opts into); nothing system-wide is intercepted.
- Cloud workers receive the profile and the command over SSH in batch mode with no password prompts; the worker uses its own checkout, never the developer's filesystem.
- `morph.yaml` is committed without a worker host or key; credentials come from `MORPH_CLOUD_*`.

---

## 17. Glossary

| Term | Definition |
|---|---|
| **Profile** | A portable JSON description of a machine's environment conditions, one `{value, status}` per field |
| **Capture / Define** | Recording a real machine's conditions / typing a target by hand |
| **Reproduction** | Applying a profile's conditions on another machine; per-field fidelity says how |
| **Baseline** | Trials under the unconstrained host |
| **Treatment / candidate** | Trials with one condition (or the full target) applied |
| **Pair** | One baseline trial and one treatment trial run back to back in the same round |
| **E-value** | Anytime-valid evidence against "no difference"; reject at `K/alpha` |
| **Isolation** | Determining which condition raises the failure rate |
| **Interaction** | A failure that only occurs when two conditions are combined |
| **Threshold / boundary** | The parameter value where failures begin; reported as a credible interval |
| **Minimal set** | The 1-minimal subset of conditions that still reproduces the failure (ddmin) |
| **Environment-caused / exposed / application-internal / no effect** | The four-way verdict |
| **Invalid trial** | A run the app could not attempt (exit 2, 126, 127, launch failure); retried, never counted |
| **Fidelity** | Per-field record of the mechanism actually used and its status |
| **Regression bundle** | A saved, replayable record of a discovered failure and its conditions |
| **Adapter** | Platform-specific application of conditions; `ProxyAdapter` is the unprivileged fallback |
| **User-space proxy** | A TCP relay with an RTT delay line and an RTO-based loss model, no kernel access needed |
