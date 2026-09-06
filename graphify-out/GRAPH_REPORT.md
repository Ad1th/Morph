# Graph Report - .  (2026-09-06)

## Corpus Check
- Corpus is ~15,356 words - fits in a single context window. You may not need a graph.

## Summary
- 33 nodes · 30 edges · 8 communities detected
- Extraction: 90% EXTRACTED · 10% INFERRED · 0% AMBIGUOUS · INFERRED: 3 edges (avg confidence: 0.78)
- Token cost: 1,200 input · 800 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Experiment Engine & Causal Statistics|Experiment Engine & Causal Statistics]]
- [[_COMMUNITY_Runtime OS Adapters & Telemetry|Runtime OS Adapters & Telemetry]]
- [[_COMMUNITY_Morph Core Platform & Interfaces|Morph Core Platform & Interfaces]]
- [[_COMMUNITY_Flight Recorder & CI Regression|Flight Recorder & CI Regression]]
- [[_COMMUNITY_Environment Capture & Profiler Schema|Environment Capture & Profiler Schema]]
- [[_COMMUNITY_Failure Corpus Timeout Scenario|Failure Corpus: Timeout Scenario]]
- [[_COMMUNITY_Failure Corpus Race Condition|Failure Corpus: Race Condition]]
- [[_COMMUNITY_Failure Corpus Locale Formatting|Failure Corpus: Locale Formatting]]

## God Nodes (most connected - your core abstractions)
1. `Experiment Engine` - 9 edges
2. `Morph Core Platform` - 8 edges
3. `BaseAdapter Interface` - 5 edges
4. `Flight Recorder (.morph)` - 3 edges
5. `Runtime Controller` - 3 edges
6. `Causal Isolation Engine` - 2 edges
7. `Environment Profiler` - 2 edges
8. `EnvironmentProfile Schema` - 2 edges
9. `Threshold Search (Binary Search)` - 2 edges
10. `Multi-Variable Interaction Detection` - 2 edges

## Surprising Connections (you probably didn't know these)
- `Experiment Engine` --references--> `SGLang Plain-English Reporter`  [INFERRED]
  architecture.md → Morph_PRD.md
- `Experiment Engine` --references--> `ElevenLabs Voice Announcer`  [INFERRED]
  architecture.md → Morph_PRD.md
- `Morph Core Platform` --implements--> `Environment Twin`  [EXTRACTED]
  architecture.md → README.md
- `Morph Core Platform` --references--> `Tin Cloud Fallback Worker`  [EXTRACTED]
  architecture.md → Morph_PRD.md
- `Morph Core Platform` --references--> `n8n CI Workflow Orchestrator`  [EXTRACTED]
  architecture.md → Morph_PRD.md

## Hyperedges (group relationships)
- **Cross-Platform Runtime Adapters** — base_adapter, adapter_windows, adapter_macos, adapter_linux, user_space_proxy [EXTRACTED 1.00]
- **Statistical Causal Isolation Loop** — experiment_engine, baseline_treatment, threshold_search, interaction_detection, fisher_exact_test, failure_classifier [EXTRACTED 1.00]

## Communities

### Community 0 - "Experiment Engine & Causal Statistics"
Cohesion: 0.25
Nodes (9): Baseline vs Treatment Runner, ElevenLabs Voice Announcer, Experiment Engine, Failure B: Lock TTL vs Network (Flagship), Failure Classifier (Caused vs Exposed), Fisher Exact & Two-Proportion Test, Multi-Variable Interaction Detection, SGLang Plain-English Reporter (+1 more)

### Community 1 - "Runtime OS Adapters & Telemetry"
Cohesion: 0.29
Nodes (7): Linux Adapter (tc/netem/cgroups), macOS Adapter (dnctl/pfctl), Windows Adapter (Clumsy/JobObjects), BaseAdapter Interface, Runtime Controller, Telemetry Collector, User-Space TCP Proxy (AsyncIO)

### Community 2 - "Morph Core Platform & Interfaces"
Cohesion: 0.29
Nodes (7): Typer CLI Interface, Environment Twin, FastAPI API Server, React/Vite Dashboard, Morph Core Platform, n8n CI Workflow Orchestrator, Tin Cloud Fallback Worker

### Community 3 - "Flight Recorder & CI Regression"
Cohesion: 0.5
Nodes (4): Causal Isolation Engine, CI Invariant Exporter, Flight Recorder (.morph), Regression Replay Engine

### Community 4 - "Environment Capture & Profiler Schema"
Cohesion: 0.67
Nodes (3): EnvironmentProfile Schema, FieldStatus (Reproduced/Approximated/Unavailable), Environment Profiler

### Community 5 - "Failure Corpus: Timeout Scenario"
Cohesion: 1.0
Nodes (1): Failure A: Simple Timeout

### Community 6 - "Failure Corpus: Race Condition"
Cohesion: 1.0
Nodes (1): Failure C: CPU Constraint Race Condition

### Community 7 - "Failure Corpus: Locale Formatting"
Cohesion: 1.0
Nodes (1): Failure D: Locale Date Formatting

## Knowledge Gaps
- **21 isolated node(s):** `Environment Twin`, `FieldStatus (Reproduced/Approximated/Unavailable)`, `Windows Adapter (Clumsy/JobObjects)`, `macOS Adapter (dnctl/pfctl)`, `Linux Adapter (tc/netem/cgroups)` (+16 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Failure Corpus: Timeout Scenario`** (1 nodes): `Failure A: Simple Timeout`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Failure Corpus: Race Condition`** (1 nodes): `Failure C: CPU Constraint Race Condition`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Failure Corpus: Locale Formatting`** (1 nodes): `Failure D: Locale Date Formatting`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Morph Core Platform` connect `Morph Core Platform & Interfaces` to `Experiment Engine & Causal Statistics`, `Runtime OS Adapters & Telemetry`, `Environment Capture & Profiler Schema`?**
  _High betweenness centrality (0.611) - this node is a cross-community bridge._
- **Why does `Experiment Engine` connect `Experiment Engine & Causal Statistics` to `Morph Core Platform & Interfaces`, `Flight Recorder & CI Regression`?**
  _High betweenness centrality (0.527) - this node is a cross-community bridge._
- **Why does `Runtime Controller` connect `Runtime OS Adapters & Telemetry` to `Morph Core Platform & Interfaces`?**
  _High betweenness centrality (0.288) - this node is a cross-community bridge._
- **Are the 2 inferred relationships involving `Experiment Engine` (e.g. with `SGLang Plain-English Reporter` and `ElevenLabs Voice Announcer`) actually correct?**
  _`Experiment Engine` has 2 INFERRED edges - model-reasoned connections that need verification._
- **What connects `Environment Twin`, `FieldStatus (Reproduced/Approximated/Unavailable)`, `Windows Adapter (Clumsy/JobObjects)` to the rest of the system?**
  _21 weakly-connected nodes found - possible documentation gaps or missing edges._