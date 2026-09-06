# Graph Report - /Users/adith/Documents/Dev/ACTIVE/Morph  (2026-09-06)

## Corpus Check
- 7 files · ~24,114 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 67 nodes · 95 edges · 11 communities detected
- Extraction: 78% EXTRACTED · 22% INFERRED · 0% AMBIGUOUS · INFERRED: 21 edges (avg confidence: 0.64)
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

## God Nodes (most connected - your core abstractions)
1. `RunResult` - 9 edges
2. `Experiment Engine` - 9 edges
3. `EnvironmentProfile` - 8 edges
4. `Morph Core Platform` - 8 edges
5. `test_experiment_schema()` - 7 edges
6. `TrialBatch` - 5 edges
7. `ComparisonResult` - 5 edges
8. `ThresholdResult` - 5 edges
9. `ExperimentResult` - 5 edges
10. `sample_profile_dict()` - 5 edges

## Surprising Connections (you probably didn't know these)
- `Experiment Engine` --references--> `SGLang Plain-English Reporter`  [INFERRED]
  architecture.md → Morph_PRD.md
- `Experiment Engine` --references--> `ElevenLabs Voice Announcer`  [INFERRED]
  architecture.md → Morph_PRD.md
- `test_run_result_schema()` --calls--> `RunResult`  [INFERRED]
  /Users/adith/Documents/Dev/ACTIVE/Morph/tests/test_schema.py → /Users/adith/Documents/Dev/ACTIVE/Morph/morph/schema/telemetry.py
- `Morph Core Platform` --implements--> `Environment Twin`  [EXTRACTED]
  architecture.md → README.md
- `Morph Core Platform` --references--> `Tin Cloud Fallback Worker`  [EXTRACTED]
  architecture.md → Morph_PRD.md

## Hyperedges (group relationships)
- **Cross-Platform Runtime Adapters** — base_adapter, adapter_windows, adapter_macos, adapter_linux, user_space_proxy [EXTRACTED 1.00]
- **Statistical Causal Isolation Loop** — experiment_engine, baseline_treatment, threshold_search, interaction_detection, fisher_exact_test, failure_classifier [EXTRACTED 1.00]

## Communities

### Community 0 - "Community 0"
Cohesion: 0.22
Nodes (12): BaseModel, Enum, CPUInfo, FieldStatus, FilesystemInfo, LocaleInfo, MemoryInfo, NetworkInfo (+4 more)

### Community 1 - "Community 1"
Cohesion: 0.17
Nodes (13): Baseline vs Treatment Runner, Causal Isolation Engine, CI Invariant Exporter, ElevenLabs Voice Announcer, Experiment Engine, Failure B: Lock TTL vs Network (Flagship), Failure Classifier (Caused vs Exposed), Fisher Exact & Two-Proportion Test (+5 more)

### Community 2 - "Community 2"
Cohesion: 0.2
Nodes (10): Typer CLI Interface, EnvironmentProfile Schema, Environment Twin, FastAPI API Server, FieldStatus (Reproduced/Approximated/Unavailable), React/Vite Dashboard, Morph Core Platform, n8n CI Workflow Orchestrator (+2 more)

### Community 3 - "Community 3"
Cohesion: 0.56
Nodes (8): ComparisonResult, ExperimentConfig, ExperimentResult, ThresholdResult, TrialBatch, EnvironmentProfile, RunResult, test_experiment_schema()

### Community 4 - "Community 4"
Cohesion: 0.36
Nodes (6): RegressionArtifact, sample_profile_dict(), test_environment_profile_deserialization(), test_environment_profile_json_roundtrip(), test_regression_artifact_schema(), test_run_result_schema()

### Community 5 - "Community 5"
Cohesion: 0.29
Nodes (7): Linux Adapter (tc/netem/cgroups), macOS Adapter (dnctl/pfctl), Windows Adapter (Clumsy/JobObjects), BaseAdapter Interface, Runtime Controller, Telemetry Collector, User-Space TCP Proxy (AsyncIO)

### Community 6 - "Community 6"
Cohesion: 1.0
Nodes (1): Morph: Test software in environments you don't physically have.

### Community 7 - "Community 7"
Cohesion: 1.0
Nodes (0): 

### Community 8 - "Community 8"
Cohesion: 1.0
Nodes (1): Failure A: Simple Timeout

### Community 9 - "Community 9"
Cohesion: 1.0
Nodes (1): Failure C: CPU Constraint Race Condition

### Community 10 - "Community 10"
Cohesion: 1.0
Nodes (1): Failure D: Locale Date Formatting

## Knowledge Gaps
- **22 isolated node(s):** `Morph: Test software in environments you don't physically have.`, `Environment Twin`, `FieldStatus (Reproduced/Approximated/Unavailable)`, `Windows Adapter (Clumsy/JobObjects)`, `macOS Adapter (dnctl/pfctl)` (+17 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Community 6`** (2 nodes): `Morph: Test software in environments you don't physically have.`, `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 7`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 8`** (1 nodes): `Failure A: Simple Timeout`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 9`** (1 nodes): `Failure C: CPU Constraint Race Condition`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 10`** (1 nodes): `Failure D: Locale Date Formatting`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Morph Core Platform` connect `Community 2` to `Community 1`, `Community 5`?**
  _High betweenness centrality (0.141) - this node is a cross-community bridge._
- **Why does `Experiment Engine` connect `Community 1` to `Community 2`?**
  _High betweenness centrality (0.122) - this node is a cross-community bridge._
- **Why does `Runtime Controller` connect `Community 5` to `Community 2`?**
  _High betweenness centrality (0.067) - this node is a cross-community bridge._
- **Are the 7 inferred relationships involving `RunResult` (e.g. with `TrialBatch` and `ComparisonResult`) actually correct?**
  _`RunResult` has 7 INFERRED edges - model-reasoned connections that need verification._
- **Are the 2 inferred relationships involving `Experiment Engine` (e.g. with `SGLang Plain-English Reporter` and `ElevenLabs Voice Announcer`) actually correct?**
  _`Experiment Engine` has 2 INFERRED edges - model-reasoned connections that need verification._
- **Are the 6 inferred relationships involving `EnvironmentProfile` (e.g. with `RegressionArtifact` and `TrialBatch`) actually correct?**
  _`EnvironmentProfile` has 6 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Morph: Test software in environments you don't physically have.`, `Environment Twin`, `FieldStatus (Reproduced/Approximated/Unavailable)` to the rest of the system?**
  _22 weakly-connected nodes found - possible documentation gaps or missing edges._