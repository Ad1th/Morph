# Morph: Software Architecture Document

> Build guide for developers. Read this, understand the system, build it.

This document describes every module, interface, data flow, and file structure in Morph. It is derived from the [Morph PRD](./Morph_PRD.md) and covers the full system: from environment capture through causal isolation to regression export.

---

## 1. System Overview

Morph is a local-first developer tool that:

1. **Captures** environment conditions from a machine (OS, CPU, RAM, locale, network).
2. **Reproduces** those conditions on a different machine using OS-native controls.
3. **Runs** an application under those reproduced conditions and collects telemetry.
4. **Experiments** by varying conditions systematically (baseline vs. treatment, threshold search).
5. **Isolates** the exact environmental condition (or combination) responsible for the failure.
6. **Exports** the discovered failure as a replayable regression artifact.

### Core Loop

```
CAPTURE/DEFINE --> REPRODUCE --> RUN --> OBSERVE --> VARY --> ISOLATE --> FIX --> REPLAY --> PASS
```

### High-Level Architecture

```
                         Morph UI
                    Dashboard / CLI
                           |
                    Local Controller
                           |
          +----------------+----------------+
          |                |                |
       Profiler          Runtime       Experiment
          |                |              Engine
          +----------------+----------------+
                           |
                      OS Adapter
             +-------------+-------------+
             |             |             |
           macOS        Windows        Linux
             |             |             |
             +-------------+-------------+
                           |
                    Target Process
                           |
                       Telemetry
```

---

## 2. Module Inventory

| Module | Directory | Responsibility | Language |
|---|---|---|---|
| CLI | `morph/cli/` | Command-line entry point (Typer + Rich) | Python |
| API Server | `morph/api/` | FastAPI server for frontend communication | Python |
| Profiler | `morph/profiler/` | Captures machine environment into a profile | Python |
| Runtime | `morph/runtime/` | Applies environment conditions, launches target process | Python |
| OS Adapters | `morph/runtime/adapters/` | Platform-specific implementations (macOS, Windows, Linux) | Python |
| Experiment Engine | `morph/engine/` | Baseline/treatment runner, statistical comparison, threshold search | Python |
| Telemetry | `morph/telemetry/` | Collects stdout/stderr, exit codes, timing, resource usage | Python |
| Regression | `morph/regression/` | Saves/loads/replays `.morph` regression artifacts | Python |
| Schema | `morph/schema/` | Pydantic models for profiles, results, telemetry | Python |
| Demo Apps | `demo_apps/` | Deliberately buggy sample applications for demonstration | Python |
| Frontend | `frontend/` | React + TypeScript + Vite dashboard | TypeScript |
| Tests | `tests/` | pytest test suite | Python |

---

## 3. Directory Structure

```
morph/
  __init__.py
  __main__.py                    # python -m morph entry point

  cli/
    __init__.py
    main.py                      # Typer app: capture, run, experiment, replay
    display.py                   # Rich tables, progress bars, result formatting

  api/
    __init__.py
    server.py                    # FastAPI app
    routes/
      profiles.py                # GET/POST /profiles
      runs.py                    # POST /run, GET /runs/{id}
      experiments.py             # POST /experiment, GET /experiments/{id}
      regressions.py             # GET/POST /regressions

  schema/
    __init__.py
    profile.py                   # EnvironmentProfile pydantic model
    telemetry.py                 # RunResult, TelemetryData models
    experiment.py                # ExperimentConfig, ExperimentResult models
    regression.py                # RegressionArtifact model
    comparison.py                # ComparisonResult, ThresholdResult models

  profiler/
    __init__.py
    capture.py                   # Main capture orchestrator
    collectors/
      __init__.py
      cpu.py                     # CPU info: cores, arch, clock (psutil + py-cpuinfo)
      memory.py                  # RAM total/available (psutil)
      os_info.py                 # OS family, version, build (platform + distro)
      locale_info.py             # Locale, timezone (stdlib locale + tzdata)
      network.py                 # Measured latency, loss estimate, bandwidth
      filesystem.py              # Case sensitivity, path separator, locking behavior
      runtime_env.py             # Python version, env vars, dependency versions

  runtime/
    __init__.py
    controller.py                # Orchestrates: load profile -> apply conditions -> run -> collect
    runner.py                    # Subprocess launcher with telemetry collection
    adapters/
      __init__.py
      base.py                    # Abstract BaseAdapter interface
      macos.py                   # macOS: dnctl/pfctl for network, process priority for CPU
      windows.py                 # Windows: Clumsy or proxy for network, Job Objects for CPU
      linux.py                   # Linux: tc/netem for network, cgroups for CPU/memory
      proxy.py                   # User-space TCP proxy for network simulation (cross-platform)

  engine/
    __init__.py
    experiment.py                # Main experiment loop: baseline, treatments, isolation
    comparison.py                # Statistical comparison (Fisher exact, two-proportion z-test)
    threshold.py                 # Binary search for failure boundary
    grid.py                      # 2D parameter grid search (latency x loss, etc.)
    classifier.py                # Classifies: environment-caused vs environment-exposed

  telemetry/
    __init__.py
    collector.py                 # Wraps subprocess, captures stdout/stderr/timing/resources
    parser.py                    # Extracts exit code, error type, stack trace from output

  regression/
    __init__.py
    artifact.py                  # Creates .morph/ regression directories
    replay.py                    # Loads and replays a saved regression
    exporter.py                  # Generates standalone test files (test_morph_invariant.py)

demo_apps/
  checkout_service/
    demo_app.py                  # Failure B: lock lease timeout under latency + packet loss
    README.md
  timeout_client/
    demo_app.py                  # Failure A: simple HTTP timeout under high latency
    README.md
  race_condition/
    demo_app.py                  # Failure C: concurrency bug exposed by CPU constraint
    README.md
  locale_parser/
    demo_app.py                  # Failure D: date parser with wrong locale assumption
    README.md

frontend/
  package.json
  vite.config.ts
  src/
    App.tsx
    main.tsx
    api/
      client.ts                  # HTTP client to FastAPI backend
    pages/
      EnvironmentPage.tsx        # Profile capture/define, comparison view
      ReproductionPage.tsx       # REPRODUCED/APPROXIMATED/UNAVAILABLE status per field
      ExperimentPage.tsx         # Live trial results table, progress
      CausePage.tsx              # Final isolation result, threshold, interaction evidence
      RegressionPage.tsx         # Saved regressions, replay controls
    components/
      ProfileCard.tsx
      ComparisonTable.tsx
      TrialResultsTable.tsx
      ThresholdGauge.tsx
      FailureTimeline.tsx
      StatusBadge.tsx            # REPRODUCED / APPROXIMATED / UNAVAILABLE badges

tests/
  test_profiler.py
  test_schema.py
  test_engine.py
  test_comparison.py
  test_threshold.py
  test_runner.py
  test_regression.py
  test_api.py
  conftest.py

.morph/                          # Generated at runtime
  regressions/
    timeout-001/
      environment.json
      command.json
      expected.json
      metadata.json
```

---

## 4. Data Models (Schema)

### 4.1 Environment Profile (`schema/profile.py`)

The portable JSON format that describes a machine. Every field carries a `status` indicating how it was handled.

```python
from pydantic import BaseModel
from typing import Optional, Literal, Any
from enum import Enum

class FieldStatus(str, Enum):
    CAPTURED = "captured"         # Measured from a real machine
    REQUESTED = "requested"       # Defined manually by the developer
    REPRODUCED = "reproduced"     # Successfully applied on the test machine
    APPROXIMATED = "approximated" # Best-effort (e.g., CPU throttled but not identical)
    UNAVAILABLE = "unavailable"   # Cannot be reproduced locally

class ProfileField(BaseModel):
    value: Any
    status: FieldStatus = FieldStatus.REQUESTED

class OSInfo(BaseModel):
    family: ProfileField          # "windows" | "darwin" | "linux"
    version: ProfileField         # "11", "14.5", "22.04"

class CPUInfo(BaseModel):
    architecture: ProfileField    # "x86_64" | "arm64"
    cores: ProfileField           # Physical core count
    logical_processors: ProfileField
    clock_mhz: ProfileField

class MemoryInfo(BaseModel):
    total_mb: ProfileField

class LocaleInfo(BaseModel):
    locale: ProfileField          # "en-IN", "en-US"
    timezone: ProfileField        # "Asia/Kolkata"

class FilesystemInfo(BaseModel):
    case_sensitive: ProfileField

class NetworkInfo(BaseModel):
    latency_ms: ProfileField
    packet_loss_percent: ProfileField
    bandwidth_mbps: Optional[ProfileField] = None

class EnvironmentProfile(BaseModel):
    version: str = "1.0"
    os: OSInfo
    cpu: CPUInfo
    memory: MemoryInfo
    locale: LocaleInfo
    filesystem: Optional[FilesystemInfo] = None
    network: NetworkInfo
```

### Example Profile JSON

```json
{
  "version": "1.0",
  "os": {
    "family": {"value": "windows", "status": "captured"},
    "version": {"value": "11", "status": "captured"}
  },
  "cpu": {
    "architecture": {"value": "x86_64", "status": "captured"},
    "cores": {"value": 4, "status": "captured"},
    "logical_processors": {"value": 4, "status": "captured"},
    "clock_mhz": {"value": 2400, "status": "captured"}
  },
  "memory": {
    "total_mb": {"value": 8192, "status": "captured"}
  },
  "locale": {
    "locale": {"value": "en-IN", "status": "captured"},
    "timezone": {"value": "Asia/Kolkata", "status": "captured"}
  },
  "filesystem": {
    "case_sensitive": {"value": false, "status": "captured"}
  },
  "network": {
    "latency_ms": {"value": 180, "status": "captured"},
    "packet_loss_percent": {"value": 2.0, "status": "captured"},
    "bandwidth_mbps": {"value": 10, "status": "captured"}
  }
}
```

### 4.2 Run Result (`schema/telemetry.py`)

```python
class RunResult(BaseModel):
    run_id: str
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: float
    peak_memory_mb: Optional[float] = None
    passed: bool                  # exit_code == 0
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    timestamp: str
```

### 4.3 Experiment Result (`schema/experiment.py`)

```python
class TrialBatch(BaseModel):
    condition_label: str          # "baseline", "latency_180ms", "loss_2pct", "latency+loss"
    profile_overrides: dict       # Which profile fields were changed
    total_runs: int
    failures: int
    failure_rate: float
    run_results: list[RunResult]

class ComparisonResult(BaseModel):
    baseline: TrialBatch
    treatment: TrialBatch
    p_value: Optional[float] = None
    is_significant: bool
    effect_label: str             # "no_effect" | "significant_increase" | "significant_decrease"

class ThresholdResult(BaseModel):
    parameter: str                # "network.latency_ms"
    safe_value: float             # Highest value that still passes
    failure_value: float          # Lowest value that fails
    boundary_estimate: float      # Midpoint or interpolated boundary
    search_points: list[dict]     # [{"value": 150, "passed": true}, ...]

class ExperimentResult(BaseModel):
    experiment_id: str
    target_profile: EnvironmentProfile
    comparisons: list[ComparisonResult]
    interactions: list[ComparisonResult]   # Multi-variable combinations
    thresholds: list[ThresholdResult]
    classification: str           # "environment_caused" | "environment_exposed" | "application_internal"
    strongest_condition: str
    summary: str
```

### 4.4 Regression Artifact (`schema/regression.py`)

```python
class RegressionArtifact(BaseModel):
    regression_id: str
    environment: EnvironmentProfile
    command: str
    expected_exit_code: int
    expected_max_failure_rate: float
    failure_signature: Optional[str] = None
    created_at: str
    metadata: dict
```

---

## 5. Module Deep Dives

### 5.1 Profiler (`morph/profiler/`)

**Purpose:** Capture the current machine environment into an `EnvironmentProfile` JSON.

**Entry point:** `capture.py`

```python
# capture.py (simplified interface)
def capture_environment() -> EnvironmentProfile:
    """Collects all environment data and returns a structured profile."""
    return EnvironmentProfile(
        os=collect_os(),
        cpu=collect_cpu(),
        memory=collect_memory(),
        locale=collect_locale(),
        filesystem=collect_filesystem(),
        network=collect_network(),
    )
```

**Collectors** (each in `collectors/`):

| Collector | Source Libraries | What It Reads |
|---|---|---|
| `cpu.py` | `psutil`, `py-cpuinfo` | `psutil.cpu_count()`, `cpuinfo.get_cpu_info()` |
| `memory.py` | `psutil` | `psutil.virtual_memory().total` |
| `os_info.py` | `platform`, `distro` | `platform.system()`, `platform.version()`, `distro.id()` |
| `locale_info.py` | `locale`, `time`, `tzdata` | `locale.getdefaultlocale()`, `time.tzname` |
| `network.py` | `subprocess` (ping), `socket` | Measures RTT to a known endpoint, estimates loss |
| `filesystem.py` | `os`, `tempfile` | Creates temp files to test case sensitivity |
| `runtime_env.py` | `sys`, `os` | `sys.version`, `os.environ`, installed packages |

**Output:** Writes `profile.json` to disk. Every field status is set to `captured`.

---

### 5.2 Runtime Controller (`morph/runtime/`)

**Purpose:** Load a profile, apply conditions via the OS adapter, run the target process, collect telemetry, clean up.

**Lifecycle:**

```
controller.run(profile, command)
    |
    +--> adapter.apply_network(latency_ms, packet_loss_pct)
    +--> adapter.apply_cpu(cores)
    +--> adapter.apply_memory(limit_mb)  [if supported]
    +--> adapter.apply_locale(locale, timezone)
    |
    +--> runner.execute(command)
    |       |
    |       +--> subprocess.Popen(command, env=modified_env)
    |       +--> capture stdout, stderr, timing, exit code
    |       +--> return RunResult
    |
    +--> adapter.cleanup()
    |
    +--> return RunResult
```

**Key Design Decision: The Adapter Interface**

```python
# adapters/base.py
from abc import ABC, abstractmethod

class BaseAdapter(ABC):

    @abstractmethod
    def apply_network(self, latency_ms: float, packet_loss_pct: float,
                      bandwidth_mbps: float | None = None) -> None: ...

    @abstractmethod
    def apply_cpu(self, max_cores: int) -> None: ...

    @abstractmethod
    def apply_memory(self, limit_mb: int) -> None: ...

    @abstractmethod
    def apply_locale(self, locale_str: str, timezone: str) -> None: ...

    @abstractmethod
    def cleanup(self) -> None: ...

    @abstractmethod
    def capabilities(self) -> dict[str, bool]: ...
```

Each OS adapter implements this interface using platform-native tools:

| Condition | macOS | Windows | Linux |
|---|---|---|---|
| Network shaping | `dnctl` + `pfctl` pipes, or user-space proxy | Clumsy, or user-space proxy | `tc qdisc netem` |
| CPU restriction | `taskpolicy`, process affinity | Job Objects (`CreateJobObject`) | cgroups v2 |
| Memory limit | Not natively supported (use ulimit) | Job Objects | cgroups v2 |
| Locale/Timezone | `LC_ALL`, `TZ` env vars | `LC_ALL`, `TZ` env vars | `LC_ALL`, `TZ` env vars |

**Cross-Platform Fallback: User-Space TCP Proxy (`adapters/proxy.py`)**

For network simulation without administrator privileges or kernel modules:

```
Target App --> localhost:PROXY_PORT --> [inject delay, drop packets] --> upstream destination
```

This is implemented as a simple async TCP relay using Python stdlib `asyncio`. It intercepts outbound connections from the demo app and injects:
- `asyncio.sleep(latency_ms / 1000)` before forwarding each packet.
- `random.random() < packet_loss_pct / 100` to drop packets probabilistically.

This proxy is the **recommended default** for hackathon demos because it requires zero OS permissions and never crashes on unfamiliar Wi-Fi.

---

### 5.3 Experiment Engine (`morph/engine/`)

**Purpose:** Run controlled experiments to isolate which environmental condition causes the failure.

**Three modes of operation:**

#### Mode 1: Single-Variable Isolation (`experiment.py`)

```
For each candidate variable (latency, loss, CPU, locale, ...):
    1. Run N trials under BASELINE conditions --> baseline_failures
    2. Run N trials under TREATMENT (change one variable) --> treatment_failures
    3. Compare failure rates statistically
    4. If significantly different, mark as candidate cause
```

#### Mode 2: Threshold Search (`threshold.py`)

```
Given a candidate variable (e.g., latency_ms):
    low = safe_value (e.g., 50 ms, known to pass)
    high = failure_value (e.g., 300 ms, known to fail)

    While (high - low) > precision:
        mid = (low + high) / 2
        Run N trials at mid
        If failure_rate > threshold:
            high = mid
        Else:
            low = mid

    Return boundary_estimate = (low + high) / 2
```

#### Mode 3: Interaction Detection (`experiment.py`)

```
For each pair of candidate variables (A, B):
    Run trials with: neither, A only, B only, A+B

    If A alone and B alone both pass, but A+B fails:
        Report INTERACTION between A and B
```

**Statistical Comparison (`comparison.py`):**

```python
from scipy.stats import fisher_exact

def compare_failure_rates(baseline_fails, baseline_total,
                          treatment_fails, treatment_total) -> ComparisonResult:
    """
    Fisher's exact test for small sample sizes.
    Two-proportion z-test for larger samples (N > 30).
    """
    table = [[baseline_fails, baseline_total - baseline_fails],
             [treatment_fails, treatment_total - treatment_fails]]
    odds_ratio, p_value = fisher_exact(table)

    return ComparisonResult(
        p_value=p_value,
        is_significant=(p_value < 0.05),
        effect_label="significant_increase" if p_value < 0.05 and
                     treatment_fails/treatment_total > baseline_fails/baseline_total
                     else "no_effect"
    )
```

**Failure Classification (`classifier.py`):**

| Classification | Condition |
|---|---|
| `application_internal` | Baseline failure rate is already high (> 10%) regardless of environment changes |
| `environment_caused` | Baseline near 0% failures; treatment shows statistically significant increase |
| `environment_exposed` | Baseline has low but nonzero failures; treatment dramatically amplifies rate |

---

### 5.4 Telemetry Collector (`morph/telemetry/`)

**Purpose:** Wrap subprocess execution and extract structured data from each run.

```python
# collector.py
import subprocess, time
from datetime import datetime

def run_with_telemetry(command: str, env: dict, timeout: float = 30.0) -> RunResult:
    start = time.time()
    proc = subprocess.Popen(
        command, shell=True, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        stdout, stderr = proc.communicate()

    duration = (time.time() - start) * 1000

    return RunResult(
        exit_code=proc.returncode,
        stdout=stdout.decode(errors="replace"),
        stderr=stderr.decode(errors="replace"),
        duration_ms=duration,
        passed=(proc.returncode == 0),
        error_type=extract_error_type(stderr.decode(errors="replace")),
        error_message=extract_error_message(stderr.decode(errors="replace")),
        timestamp=datetime.utcnow().isoformat(),
    )
```

---

### 5.5 Regression Artifacts (`morph/regression/`)

**Purpose:** Save a discovered failure as a replayable, portable artifact.

**Directory structure generated:**

```
.morph/
  regressions/
    checkout-latency-001/
      environment.json      # The EnvironmentProfile that triggers the failure
      command.json           # {"command": "python demo_app.py", "timeout": 30}
      expected.json          # {"exit_code": 0, "max_failure_rate": 0.01}
      metadata.json          # {"created": "...", "failure_signature": "LockLostException", ...}
```

**Replay:**

```bash
morph replay .morph/regressions/checkout-latency-001
```

This loads `environment.json`, applies it via the runtime controller, runs the command, and verifies the outcome matches `expected.json`.

**CI Invariant Export (`exporter.py`):**

Generates a standalone test file:

```python
# test_morph_invariant.py (generated)
import subprocess

def test_checkout_environment_tolerance():
    """Generated by Morph: verifies service survives user baseline."""
    # In a real setup, morph.environment() applies the proxy conditions
    result = subprocess.run(["python", "demo_app.py"], capture_output=True)
    assert result.returncode == 0
```

---

## 6. API Contract (`morph/api/`)

### Endpoints

| Method | Path | Request Body | Response | Purpose |
|---|---|---|---|---|
| `POST` | `/profiles/capture` | None | `EnvironmentProfile` | Capture current machine |
| `POST` | `/profiles` | `EnvironmentProfile` | `{"id": "..."}` | Save a manually defined profile |
| `GET` | `/profiles` | None | `list[EnvironmentProfile]` | List all saved profiles |
| `GET` | `/profiles/{id}` | None | `EnvironmentProfile` | Get one profile |
| `POST` | `/run` | `{"profile_id": "...", "command": "..."}` | `RunResult` | Single run under a profile |
| `POST` | `/experiment` | `ExperimentConfig` | `ExperimentResult` | Full experiment (baseline + treatments) |
| `GET` | `/experiments/{id}` | None | `ExperimentResult` | Get experiment results |
| `POST` | `/regressions` | `{"experiment_id": "..."}` | `RegressionArtifact` | Save experiment as regression |
| `POST` | `/regressions/{id}/replay` | None | `RunResult` | Replay a saved regression |

### WebSocket (optional, for live updates)

| Path | Direction | Payload | Purpose |
|---|---|---|---|
| `/ws/experiment/{id}` | Server to Client | `{"trial": 3, "condition": "latency_180ms", "passed": false}` | Stream live trial results to dashboard |

---

## 7. CLI Interface (`morph/cli/`)

```bash
# Capture the current machine environment
morph capture --output profile.json

# Define a profile manually (or edit an existing one)
morph define --template default --output target.json

# Run an application under a specific profile
morph run --profile target.json --command "python demo_app.py"

# Run a full experiment (baseline + all candidate treatments)
morph experiment --profile target.json --command "python demo_app.py" --trials 5

# Search for the failure threshold of a specific parameter
morph threshold --profile target.json --command "python demo_app.py" \
    --parameter network.latency_ms --low 50 --high 300 --trials 5

# Replay a saved regression
morph replay .morph/regressions/checkout-latency-001

# Export a CI test from an experiment result
morph export --experiment-id abc123 --output test_morph_invariant.py

# Start the API server (for frontend)
morph serve --port 8000
```

---

## 8. Frontend Architecture (`frontend/`)

### Tech Stack

- React 18 + TypeScript
- Vite for build/dev
- Lightweight component library (or plain CSS modules)
- HTTP client: `fetch` or a thin wrapper

### Page Flow

```
Environment Page --> Reproduction Page --> Experiment Page --> Cause Page --> Regression Page
      |                    |                    |                  |               |
  [Capture or        [Shows field-        [Live trial        [Isolation      [Save as
   define a           level status:        progress and       result and      regression,
   profile]           REPRODUCED /         comparison         threshold       replay
                      APPROXIMATED /       tables]            display]        after fix]
                      UNAVAILABLE]
```

### Key UI Components

| Component | Data Source | What It Shows |
|---|---|---|
| `ProfileCard` | `EnvironmentProfile` | OS, CPU, RAM, locale, network at a glance |
| `ComparisonTable` | `list[ComparisonResult]` | Condition / Trials / Failures / Result per row |
| `StatusBadge` | `FieldStatus` | Green REPRODUCED, Yellow APPROXIMATED, Red UNAVAILABLE |
| `ThresholdGauge` | `ThresholdResult` | Visual slider showing the safe/fail boundary |
| `FailureTimeline` | `RunResult` | Visual timeline of lock acquire, payment, timeout |

---

## 9. Data Flow: End-to-End Walkthrough

### Scenario: Diagnosing a checkout timeout

```
Step 1: Developer defines target profile
        {latency: 180ms, loss: 2%, cores: 4, locale: en-IN}
                            |
                            v
Step 2: CLI or UI sends to Runtime Controller
        controller.run(profile, "python demo_app.py")
                            |
                            v
Step 3: OS Adapter applies conditions
        proxy.apply_network(latency=180, loss=2)
        adapter.apply_cpu(cores=4)
        adapter.apply_locale("en-IN", "Asia/Kolkata")
                            |
                            v
Step 4: Runner launches subprocess
        Popen("python demo_app.py", env=modified_env)
        Captures stdout, stderr, exit code, duration
                            |
                            v
Step 5: Adapter cleans up conditions
        proxy.cleanup()
                            |
                            v
Step 6: RunResult returned
        {exit_code: 1, error: "LockLostException", duration: 245ms}
                            |
                            v
Step 7: Experiment Engine runs controlled variations
        Baseline (normal)     --> 0/5 failures
        Latency only (180ms)  --> 0/5 failures
        Loss only (2%)        --> 0/5 failures
        Latency + Loss        --> 5/5 failures
                            |
                            v
Step 8: Statistical comparison
        Fisher exact test on each treatment vs baseline
        Latency+Loss p-value < 0.001 --> SIGNIFICANT
                            |
                            v
Step 9: Threshold search (if time permits)
        Binary search on latency with loss=2% held constant
        150ms PASS --> 200ms FAIL --> 175ms PASS --> 185ms FAIL
        Boundary: ~180ms
                            |
                            v
Step 10: Classification
         Baseline: 0% failure, Treatment: 100% failure
         Classification: ENVIRONMENT_CAUSED
         Strongest condition: latency + packet_loss interaction
                            |
                            v
Step 11: Display result in CLI/Dashboard
         ComparisonTable + ThresholdGauge + FailureTimeline
                            |
                            v
Step 12: Developer fixes demo_app.py (increases lock TTL)
                            |
                            v
Step 13: Replay same profile
         controller.run(same_profile, "python demo_app.py")
         --> 0/5 failures --> PASS
                            |
                            v
Step 14: Save as regression artifact
         .morph/regressions/checkout-latency-001/
```

---

## 10. Environment Comparison Logic

When a target profile is loaded on a different machine, Morph compares each field:

```python
def compare_profiles(target: EnvironmentProfile,
                     current: EnvironmentProfile) -> dict[str, FieldStatus]:
    result = {}

    # OS family
    if target.os.family.value == current.os.family.value:
        result["os.family"] = FieldStatus.REPRODUCED
    else:
        result["os.family"] = FieldStatus.UNAVAILABLE

    # CPU cores (can throttle down, not up)
    if current.cpu.cores.value >= target.cpu.cores.value:
        result["cpu.cores"] = FieldStatus.REPRODUCED
    else:
        result["cpu.cores"] = FieldStatus.APPROXIMATED

    # Memory (can limit down, not up)
    if current.memory.total_mb.value >= target.memory.total_mb.value:
        result["memory"] = FieldStatus.REPRODUCED
    else:
        result["memory"] = FieldStatus.UNAVAILABLE

    # Network (always reproducible via proxy)
    result["network.latency"] = FieldStatus.REPRODUCED
    result["network.loss"] = FieldStatus.REPRODUCED

    # Locale/Timezone (always reproducible via env vars)
    result["locale"] = FieldStatus.REPRODUCED
    result["timezone"] = FieldStatus.REPRODUCED

    return result
```

If any field is `UNAVAILABLE`, Morph either:
1. Warns the developer and proceeds without that condition.
2. Routes the run to a cloud worker with the required resources.

---

## 11. Demo Failure Corpus

### Failure A: Simple Timeout (Priority: Review 1)

An HTTP client calls a server with a 200ms timeout. Under 250ms+ latency, it fails.

### Failure B: Interaction Effect (Priority: Review 1, Flagship)

The checkout service with a 200ms inventory lock lease. Payment calls through the network. Under latency + packet loss, the payment succeeds but the lock expires before the response returns. Customer is charged, order is lost.

This is the primary demo because it proves Morph can detect multi-variable interactions.

### Failure C: Race Condition (Priority: Review 2)

A multi-threaded counter with an unsynchronized increment. Under full CPU, the race window is too small to hit. Under 2-core CPU constraint, context switching exposes the race.

### Failure D: Locale (Priority: Review 2)

A date parser assumes `MM/DD/YYYY` format. Under `en-IN` locale, the system returns `DD/MM/YYYY`, causing silent data corruption.

---

## 12. Cloud Fallback Architecture

```
Profile loaded
      |
      v
Local capability check
      |
  Can reproduce locally?
      |           |
     YES          NO
      |           |
  Local run    Send profile to cloud worker (Tin Computer API)
      |           |
      |        Worker applies conditions
      |        Worker runs application
      |        Worker returns telemetry
      |           |
      v           v
   RunResult   RunResult
```

Cloud workers receive the same `EnvironmentProfile` JSON. They run the same OS adapter logic on a machine with the required physical resources.

---

## 13. Configuration

### `morph.yaml` (project-level)

```yaml
version: "1.0"
default_trials: 5
significance_level: 0.05
default_command: "python demo_apps/checkout_service/demo_app.py"
proxy_port: 9876
adapters:
  network: proxy          # "proxy" | "native"
  cpu: native
cloud:
  enabled: false
  provider: tin
  endpoint: "https://api.tin.computer/v1"
```

---

## 14. Error Handling Rules

1. **Adapter failures are not silent:** If `apply_network()` fails, the run must not proceed as if conditions were applied. Raise, log, and report `UNAVAILABLE`.
2. **Subprocess timeouts:** Default 30s. Configurable. Timeout counts as a failure (exit code -1).
3. **Partial reproduction:** If 3 out of 5 conditions are applied, mark the missing ones as `UNAVAILABLE` in the result. Never claim full reproduction when conditions were skipped.
4. **Network proxy crashes:** If the proxy dies mid-run, all trials in that batch are invalidated and re-queued.

---

## 15. Testing Strategy

| Test Type | Scope | Tool | When |
|---|---|---|---|
| Unit tests | Schema validation, comparison math, threshold search, classification | pytest | Every commit |
| Integration tests | Profiler captures real data, runner executes real subprocess | pytest | Every commit |
| Demo app tests | Each demo app fails/passes under expected conditions | pytest + morph CLI | Pre-merge |
| API tests | FastAPI endpoint contracts | pytest + httpx | Pre-merge |
| Frontend smoke | Dashboard loads, displays mock data | Manual or Playwright | Pre-review |
| End-to-end | Full loop: capture, reproduce, experiment, isolate, replay | Manual + scripted | Pre-demo |

---

## 16. Security and Privacy

- Profiler captures only application-relevant data. No browser history, no user documents, no credentials.
- Environment profiles should not contain API keys or secrets from `os.environ`. Filter known sensitive keys (`AWS_SECRET`, `DATABASE_URL`, `API_KEY`, etc.).
- Network proxy only intercepts traffic from the target subprocess, not system-wide.
- Cloud workers receive only the profile and the application binary/command. No access to the developer's filesystem.

---

## 17. Glossary

| Term | Definition |
|---|---|
| **Profile** | A portable JSON description of a machine's environment conditions |
| **Capture** | Recording a real machine's conditions into a profile |
| **Reproduction** | Applying a profile's conditions on a different machine |
| **Baseline** | Running trials under normal (unmodified) conditions |
| **Treatment** | Running trials with one or more conditions changed |
| **Isolation** | Determining which specific condition caused the failure |
| **Interaction** | A failure that only occurs when two or more conditions are combined |
| **Threshold** | The exact boundary value where a condition transitions from safe to failing |
| **Environment-caused** | A failure introduced purely by the environmental condition |
| **Environment-exposed** | A pre-existing bug amplified by the environmental condition |
| **Regression artifact** | A saved, replayable record of a discovered failure and its conditions |
| **OS Adapter** | Platform-specific implementation of condition application |
| **User-space proxy** | A TCP relay that injects latency and packet loss without kernel access |
