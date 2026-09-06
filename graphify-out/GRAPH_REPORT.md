# Graph Report - /Users/adith/Documents/Dev/ACTIVE/Morph  (2026-09-06)

## Corpus Check
- 15 files · ~28,229 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 129 nodes · 241 edges · 15 communities detected
- Extraction: 65% EXTRACTED · 35% INFERRED · 0% AMBIGUOUS · INFERRED: 84 edges (avg confidence: 0.73)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 13|Community 13]]
- [[_COMMUNITY_Community 14|Community 14]]

## God Nodes (most connected - your core abstractions)
1. `run_with_telemetry()` - 24 edges
2. `RunResult` - 16 edges
3. `extract_error_type()` - 15 edges
4. `execute_command()` - 13 edges
5. `extract_error_message()` - 13 edges
6. `_py()` - 10 edges
7. `_py()` - 10 edges
8. `Experiment Engine` - 9 edges
9. `EnvironmentProfile` - 8 edges
10. `Morph Core Platform` - 8 edges

## Surprising Connections (you probably didn't know these)
- `Experiment Engine` --references--> `SGLang Plain-English Reporter`  [INFERRED]
  architecture.md → Morph_PRD.md
- `Experiment Engine` --references--> `ElevenLabs Voice Announcer`  [INFERRED]
  architecture.md → Morph_PRD.md
- `Thin dispatch layer: merge env overrides onto os.environ, then run with telemetr` --uses--> `RunResult`  [INFERRED]
  /Users/adith/Documents/Dev/ACTIVE/Morph/morph/runtime/runner.py → /Users/adith/Documents/Dev/ACTIVE/Morph/morph/schema/telemetry.py
- `Execute `command` under a copy of the current environment plus `env_overrides`.` --uses--> `RunResult`  [INFERRED]
  /Users/adith/Documents/Dev/ACTIVE/Morph/morph/runtime/runner.py → /Users/adith/Documents/Dev/ACTIVE/Morph/morph/schema/telemetry.py
- `RunResult` --calls--> `test_run_result_schema()`  [INFERRED]
  /Users/adith/Documents/Dev/ACTIVE/Morph/morph/schema/telemetry.py → /Users/adith/Documents/Dev/ACTIVE/Morph/tests/test_schema.py

## Hyperedges (group relationships)
- **Cross-Platform Runtime Adapters** — base_adapter, adapter_windows, adapter_macos, adapter_linux, user_space_proxy [EXTRACTED 1.00]
- **Statistical Causal Isolation Loop** — experiment_engine, baseline_treatment, threshold_search, interaction_detection, fisher_exact_test, failure_classifier [EXTRACTED 1.00]

## Communities

### Community 0 - "Community 0"
Cohesion: 0.21
Nodes (19): BaseModel, Enum, ComparisonResult, ExperimentConfig, ExperimentResult, ThresholdResult, TrialBatch, CPUInfo (+11 more)

### Community 1 - "Community 1"
Cohesion: 0.22
Nodes (19): extract_error_message(), extract_error_type(), extract_stack_trace(), _iter_sources(), _match(), Best-effort extraction of error type / message / stack trace from process output, Return the match that best identifies the failure in `text`.      Java header fi, test_bare_type_colon_message() (+11 more)

### Community 2 - "Community 2"
Cohesion: 0.12
Nodes (17): Linux Adapter (tc/netem/cgroups), macOS Adapter (dnctl/pfctl), Windows Adapter (Clumsy/JobObjects), BaseAdapter Interface, Typer CLI Interface, EnvironmentProfile Schema, Environment Twin, FastAPI API Server (+9 more)

### Community 3 - "Community 3"
Cohesion: 0.28
Nodes (14): execute_command(), Thin dispatch layer: merge env overrides onto os.environ, then run with telemetr, Execute `command` under a copy of the current environment plus `env_overrides`., str, _py(), test_cwd_propagates(), test_error_parsing_propagates(), test_merges_with_os_environ() (+6 more)

### Community 4 - "Community 4"
Cohesion: 0.35
Nodes (13): run_with_telemetry(), _py(), test_command_not_found(), test_cwd_is_respected(), test_empty_command_raises(), test_env_is_passed_verbatim(), test_nonzero_exit_parses_error(), test_peak_memory_reflects_allocation() (+5 more)

### Community 5 - "Community 5"
Cohesion: 0.17
Nodes (13): Baseline vs Treatment Runner, Causal Isolation Engine, CI Invariant Exporter, ElevenLabs Voice Announcer, Experiment Engine, Failure B: Lock TTL vs Network (Flagship), Failure Classifier (Caused vs Exposed), Fisher Exact & Two-Proportion Test (+5 more)

### Community 6 - "Community 6"
Cohesion: 0.24
Nodes (10): _early_result(), _kill_tree(), _monitor(), _new_run_id(), _now_iso(), Spawn a subprocess, capture output, track peak RSS + duration, kill cleanly on t, Run `command`, returning a populated RunResult.      `env`, if given, is passed, Terminate the process and every descendant; escalate to SIGKILL after a grace pe (+2 more)

### Community 7 - "Community 7"
Cohesion: 0.53
Nodes (5): sample_profile_dict(), test_environment_profile_deserialization(), test_environment_profile_json_roundtrip(), test_regression_artifact_schema(), test_run_result_schema()

### Community 8 - "Community 8"
Cohesion: 1.0
Nodes (1): Morph: Test software in environments you don't physically have.

### Community 9 - "Community 9"
Cohesion: 1.0
Nodes (0): 

### Community 10 - "Community 10"
Cohesion: 1.0
Nodes (0): 

### Community 11 - "Community 11"
Cohesion: 1.0
Nodes (0): 

### Community 12 - "Community 12"
Cohesion: 1.0
Nodes (1): Failure A: Simple Timeout

### Community 13 - "Community 13"
Cohesion: 1.0
Nodes (1): Failure C: CPU Constraint Race Condition

### Community 14 - "Community 14"
Cohesion: 1.0
Nodes (1): Failure D: Locale Date Formatting

## Knowledge Gaps
- **24 isolated node(s):** `Morph: Test software in environments you don't physically have.`, `Best-effort extraction of error type / message / stack trace from process output`, `Return the match that best identifies the failure in `text`.      Java header fi`, `Environment Twin`, `FieldStatus (Reproduced/Approximated/Unavailable)` (+19 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Community 8`** (2 nodes): `Morph: Test software in environments you don't physically have.`, `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 9`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 10`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 11`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 12`** (1 nodes): `Failure A: Simple Timeout`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 13`** (1 nodes): `Failure C: CPU Constraint Race Condition`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 14`** (1 nodes): `Failure D: Locale Date Formatting`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `run_with_telemetry()` connect `Community 4` to `Community 0`, `Community 1`, `Community 3`, `Community 6`?**
  _High betweenness centrality (0.320) - this node is a cross-community bridge._
- **Why does `RunResult` connect `Community 0` to `Community 3`, `Community 4`, `Community 6`, `Community 7`?**
  _High betweenness centrality (0.167) - this node is a cross-community bridge._
- **Why does `execute_command()` connect `Community 3` to `Community 4`?**
  _High betweenness centrality (0.107) - this node is a cross-community bridge._
- **Are the 18 inferred relationships involving `run_with_telemetry()` (e.g. with `execute_command()` and `str`) actually correct?**
  _`run_with_telemetry()` has 18 INFERRED edges - model-reasoned connections that need verification._
- **Are the 14 inferred relationships involving `RunResult` (e.g. with `Thin dispatch layer: merge env overrides onto os.environ, then run with telemetr` and `Execute `command` under a copy of the current environment plus `env_overrides`.`) actually correct?**
  _`RunResult` has 14 INFERRED edges - model-reasoned connections that need verification._
- **Are the 12 inferred relationships involving `extract_error_type()` (e.g. with `run_with_telemetry()` and `test_python_traceback_type_and_message()`) actually correct?**
  _`extract_error_type()` has 12 INFERRED edges - model-reasoned connections that need verification._
- **Are the 11 inferred relationships involving `execute_command()` (e.g. with `str` and `run_with_telemetry()`) actually correct?**
  _`execute_command()` has 11 INFERRED edges - model-reasoned connections that need verification._