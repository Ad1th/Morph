# Graph Report - /Users/adith/Documents/Dev/ACTIVE/Morph  (2026-09-06)

## Corpus Check
- 35 files · ~47,022 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 344 nodes · 507 edges · 55 communities detected
- Extraction: 58% EXTRACTED · 42% INFERRED · 0% AMBIGUOUS · INFERRED: 211 edges (avg confidence: 0.71)
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
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]
- [[_COMMUNITY_Community 18|Community 18]]
- [[_COMMUNITY_Community 19|Community 19]]
- [[_COMMUNITY_Community 20|Community 20]]
- [[_COMMUNITY_Community 21|Community 21]]
- [[_COMMUNITY_Community 22|Community 22]]
- [[_COMMUNITY_Community 23|Community 23]]
- [[_COMMUNITY_Community 24|Community 24]]
- [[_COMMUNITY_Community 25|Community 25]]
- [[_COMMUNITY_Community 26|Community 26]]
- [[_COMMUNITY_Community 27|Community 27]]
- [[_COMMUNITY_Community 28|Community 28]]
- [[_COMMUNITY_Community 29|Community 29]]
- [[_COMMUNITY_Community 30|Community 30]]
- [[_COMMUNITY_Community 31|Community 31]]
- [[_COMMUNITY_Community 32|Community 32]]
- [[_COMMUNITY_Community 33|Community 33]]
- [[_COMMUNITY_Community 34|Community 34]]
- [[_COMMUNITY_Community 35|Community 35]]
- [[_COMMUNITY_Community 36|Community 36]]
- [[_COMMUNITY_Community 37|Community 37]]
- [[_COMMUNITY_Community 38|Community 38]]
- [[_COMMUNITY_Community 39|Community 39]]
- [[_COMMUNITY_Community 40|Community 40]]
- [[_COMMUNITY_Community 41|Community 41]]
- [[_COMMUNITY_Community 42|Community 42]]
- [[_COMMUNITY_Community 43|Community 43]]
- [[_COMMUNITY_Community 44|Community 44]]
- [[_COMMUNITY_Community 45|Community 45]]
- [[_COMMUNITY_Community 46|Community 46]]
- [[_COMMUNITY_Community 47|Community 47]]
- [[_COMMUNITY_Community 48|Community 48]]
- [[_COMMUNITY_Community 49|Community 49]]
- [[_COMMUNITY_Community 50|Community 50]]
- [[_COMMUNITY_Community 51|Community 51]]
- [[_COMMUNITY_Community 52|Community 52]]
- [[_COMMUNITY_Community 53|Community 53]]
- [[_COMMUNITY_Community 54|Community 54]]

## God Nodes (most connected - your core abstractions)
1. `run_with_telemetry()` - 24 edges
2. `TrialBatch` - 22 edges
3. `RunResult` - 15 edges
4. `extract_error_type()` - 15 edges
5. `ComparisonResult` - 13 edges
6. `extract_error_message()` - 13 edges
7. `execute_command()` - 12 edges
8. `ProfileField` - 12 edges
9. `ExperimentResult` - 12 edges
10. `EnvironmentProfile` - 10 edges

## Surprising Connections (you probably didn't know these)
- `Stretch Features List (Section 37)` --semantically_similar_to--> `Not Yet Done (Out of Scope This Pass)`  [INFERRED] [semantically similar]
  docs/Morph_PRD.md → PROGRESS.md
- `Baseline vs Treatment Comparison` --semantically_similar_to--> `Experiment Engine Description (Section 15)`  [INFERRED] [semantically similar]
  README.md → docs/Morph_PRD.md
- `Environment-Exposed Application Bug` --semantically_similar_to--> `CAUSED vs EXPOSED vs INCONCLUSIVE UI States`  [INFERRED] [semantically similar]
  README.md → docs/Morph_Design_Spec.md
- `README Architecture Diagram` --semantically_similar_to--> `Morph System Overview`  [INFERRED] [semantically similar]
  README.md → docs/architecture.md
- `README Architecture Diagram` --semantically_similar_to--> `PRD Architecture Diagram`  [INFERRED] [semantically similar]
  README.md → docs/Morph_PRD.md

## Hyperedges (group relationships)
- **Cross-Platform User-Space Proxy Network Simulation** — architecture_proxy_adapter, prd_os_implementation, progress_proxy_server, readme_network_conditions_rationale [INFERRED 0.75]
- **Environment-Caused vs Environment-Exposed Classification Flow** — architecture_classifier_module, prd_environment_caused_vs_exposed_section18, design_spec_exposed_vs_caused, progress_classifier_module, progress_bug_fix_classify_failure [INFERRED 0.80]
- **Baseline/Treatment Isolation and Interaction Detection Loop** — prd_experiment_pseudocode, architecture_experiment_engine, progress_experiment_module, prd_correlation_vs_causation [INFERRED 0.75]

## Communities

### Community 0 - "Community 0"
Cohesion: 0.1
Nodes (37): classify_failure(), Causal classification: distinguishes an application bug from a failure that is g, application_internal: baseline already fails often, regardless of environment., ComparisonResult, ThresholdResult, compare_batches(), detect_interaction(), ExperimentConfig (+29 more)

### Community 1 - "Community 1"
Cohesion: 0.09
Nodes (35): BaseModel, capture_environment(), Capture orchestrator: runs all collectors and assembles an EnvironmentProfile., Collects the current machine's environment into a structured profile., collect_cpu(), CPU collector: architecture, core counts, clock speed., collect_filesystem(), Filesystem collector: detects case sensitivity by probing a temp directory. (+27 more)

### Community 2 - "Community 2"
Cohesion: 0.07
Nodes (30): Linux Adapter (tc/netem/cgroups), macOS Adapter (dnctl/pfctl), Windows Adapter (Clumsy/JobObjects), BaseAdapter Interface, Baseline vs Treatment Runner, Causal Isolation Engine, CI Invariant Exporter, Typer CLI Interface (+22 more)

### Community 3 - "Community 3"
Cohesion: 0.14
Nodes (24): _early_result(), _kill_tree(), _monitor(), _new_run_id(), _now_iso(), Spawn a subprocess, capture output, track peak RSS + duration, kill cleanly on t, Run `command`, returning a populated RunResult.      `env`, if given, is passed, Terminate the process and every descendant; escalate to SIGKILL after a grace pe (+16 more)

### Community 4 - "Community 4"
Cohesion: 0.08
Nodes (26): Failure Classification (classifier.py, Section 5.3), Experiment Engine (morph/engine/), Runtime Controller (morph/runtime/), Telemetry Collector (morph/telemetry/), Experiment Screen Design, CAUSED vs EXPOSED vs INCONCLUSIVE UI States, Root Cause View Design, Correlation vs Causation (Section 17) (+18 more)

### Community 5 - "Community 5"
Cohesion: 0.22
Nodes (19): extract_error_message(), extract_error_type(), extract_stack_trace(), _iter_sources(), _match(), Best-effort extraction of error type / message / stack trace from process output, Return the match that best identifies the failure in `text`.      Java header fi, test_bare_type_colon_message() (+11 more)

### Community 6 - "Community 6"
Cohesion: 0.12
Nodes (17): Cloud Fallback Architecture, Core Design Principle: Immersive, Linux Workspace (P2 Simplified/Recorded Fallback), Platform Priority Rationale (Windows/macOS P0, Linux P2), Cloud Fallback Requirements (Section 25), Dashboard Spec (Section 27), The One Thing Judges Need to Believe (Section 39), Judging Criteria Mapping Table (+9 more)

### Community 7 - "Community 7"
Cohesion: 0.3
Nodes (13): execute_command(), Thin dispatch layer: merge env overrides onto os.environ, then run with telemetr, Execute `command` under a copy of the current environment plus `env_overrides`., _py(), test_cwd_propagates(), test_error_parsing_propagates(), test_merges_with_os_environ(), test_no_overrides_still_inherits_environ() (+5 more)

### Community 8 - "Community 8"
Cohesion: 0.19
Nodes (5): ProxyServer, User-space TCP proxy: cross-platform network latency and packet-loss simulation., Relay chunks from reader to writer, injecting latency and packet loss., Runnable check: latency is observable, and 100% loss actually blocks delivery., _self_check()

### Community 9 - "Community 9"
Cohesion: 0.21
Nodes (8): compare_failure_rates(), Statistical comparison results: baseline vs. treatment, and threshold search., Tests for morph.engine.comparison: Fisher exact test wrapper., test_failure_rate_properties(), test_identical_rates_are_not_significant(), test_large_decrease_is_significant_decrease(), test_large_increase_is_significant_increase(), test_small_noisy_difference_is_not_significant()

### Community 10 - "Community 10"
Cohesion: 0.22
Nodes (9): API Server and Endpoints (morph/api/), CLI Interface (morph/cli/), Frontend Architecture (frontend/), Regression Artifacts (morph/regression/), Regression Artifact Format (Section 21), Stretch Features List (Section 37), Not Yet Done (Out of Scope This Pass), Local API Dependencies (fastapi, uvicorn, pydantic) (+1 more)

### Community 11 - "Community 11"
Cohesion: 0.25
Nodes (8): compare_profiles() Field Status Logic, TrialBatch/ComparisonResult/ExperimentResult Schema, EnvironmentProfile Schema, RunResult Schema, Environment Profile JSON Format (PRD), Fixed locale_info.py to Use BCP-47 Tags on Windows, Fixed os_info.py to Use distro Instead of Kernel Version, morph/schema/ Minimal Dependency Layer

### Community 12 - "Community 12"
Cohesion: 0.29
Nodes (7): BaseAdapter Interface, User-Space TCP Proxy Adapter (adapters/proxy.py), macOS Workspace (P0 Full Craft), Windows Workspace (P0 Full Craft), OS Implementation: Linux/Windows/macOS, ProxyServer Implementation (proxy.py), Why Network Conditions Specifically

### Community 13 - "Community 13"
Cohesion: 0.53
Nodes (5): sample_profile_dict(), test_environment_profile_deserialization(), test_environment_profile_json_roundtrip(), test_regression_artifact_schema(), test_run_result_schema()

### Community 14 - "Community 14"
Cohesion: 0.4
Nodes (5): Morph System Overview, PRD Architecture Diagram, PRD Purpose and Core Loop, README Architecture Diagram, Capture-Reproduce-Run-Experiment-Isolate Loop

### Community 15 - "Community 15"
Cohesion: 0.5
Nodes (4): Profiler Module (morph/profiler/), capture.py Orchestrator, Built Profiler Collectors (cpu/memory/os/locale/filesystem), Profiler Dependencies (psutil, py-cpuinfo, distro, tzdata)

### Community 16 - "Community 16"
Cohesion: 0.67
Nodes (3): Design Priority Order (Shell to Landing Page), Immersive Landing Page Concept, 24-Hour Build Plan Phases

### Community 17 - "Community 17"
Cohesion: 0.67
Nodes (3): Directory Structure Spec, Module Inventory Table, PROGRESS Task Scope (This Pass)

### Community 18 - "Community 18"
Cohesion: 1.0
Nodes (1): Morph: reproduce environment conditions and isolate the cause of failures.

### Community 19 - "Community 19"
Cohesion: 1.0
Nodes (2): Delta Debugging for CPS with Flaky Test Executions (arXiv 2607.25695), Prior Art and What's Actually New

### Community 20 - "Community 20"
Cohesion: 1.0
Nodes (2): Demo Failure Corpus (demo_apps/), Demo Failure Corpus A-D

### Community 21 - "Community 21"
Cohesion: 1.0
Nodes (2): What Morph Actually Reproduces (Targeted vs Not Claimed), README Limitations Section

### Community 22 - "Community 22"
Cohesion: 1.0
Nodes (2): Recommended Stack Decision Rationale (Section 23), Python Whole-Runtime Stack Decision

### Community 23 - "Community 23"
Cohesion: 1.0
Nodes (2): Statistical Comparison Module (comparison.py), compare_failure_rates() Implementation

### Community 24 - "Community 24"
Cohesion: 1.0
Nodes (2): Threshold Search Module (threshold.py), search_threshold() Implementation

### Community 25 - "Community 25"
Cohesion: 1.0
Nodes (0): 

### Community 26 - "Community 26"
Cohesion: 1.0
Nodes (1): Actual bound listen port (resolved after start() when listen_port=0).

### Community 27 - "Community 27"
Cohesion: 1.0
Nodes (0): 

### Community 28 - "Community 28"
Cohesion: 1.0
Nodes (0): 

### Community 29 - "Community 29"
Cohesion: 1.0
Nodes (0): 

### Community 30 - "Community 30"
Cohesion: 1.0
Nodes (0): 

### Community 31 - "Community 31"
Cohesion: 1.0
Nodes (0): 

### Community 32 - "Community 32"
Cohesion: 1.0
Nodes (0): 

### Community 33 - "Community 33"
Cohesion: 1.0
Nodes (0): 

### Community 34 - "Community 34"
Cohesion: 1.0
Nodes (1): Failure A: Simple Timeout

### Community 35 - "Community 35"
Cohesion: 1.0
Nodes (1): Failure C: CPU Constraint Race Condition

### Community 36 - "Community 36"
Cohesion: 1.0
Nodes (1): Failure D: Locale Date Formatting

### Community 37 - "Community 37"
Cohesion: 1.0
Nodes (1): The Problem: It Works On My Machine

### Community 38 - "Community 38"
Cohesion: 1.0
Nodes (1): Environment-Triggered Failure

### Community 39 - "Community 39"
Cohesion: 1.0
Nodes (1): Architecture Core Loop

### Community 40 - "Community 40"
Cohesion: 1.0
Nodes (1): RegressionArtifact Schema

### Community 41 - "Community 41"
Cohesion: 1.0
Nodes (1): Error Handling Rules

### Community 42 - "Community 42"
Cohesion: 1.0
Nodes (1): Security and Privacy Section

### Community 43 - "Community 43"
Cohesion: 1.0
Nodes (1): Signature Interaction: Enter Environment

### Community 44 - "Community 44"
Cohesion: 1.0
Nodes (1): OS-Adaptive Workspace

### Community 45 - "Community 45"
Cohesion: 1.0
Nodes (1): Color System

### Community 46 - "Community 46"
Cohesion: 1.0
Nodes (1): Typography System

### Community 47 - "Community 47"
Cohesion: 1.0
Nodes (1): Regression Test Creation Flow

### Community 48 - "Community 48"
Cohesion: 1.0
Nodes (1): Hackathon Context and Timeline

### Community 49 - "Community 49"
Cohesion: 1.0
Nodes (1): Team and Ownership (Adith/Parth/Sarthak/Rishita)

### Community 50 - "Community 50"
Cohesion: 1.0
Nodes (1): Product Scope: Pre/Post-Deployment

### Community 51 - "Community 51"
Cohesion: 1.0
Nodes (1): CI Requirements (Section 22)

### Community 52 - "Community 52"
Cohesion: 1.0
Nodes (1): Hard Cuts List (Section 36)

### Community 53 - "Community 53"
Cohesion: 1.0
Nodes (1): Review 1 Triage Cut Order (Section 38)

### Community 54 - "Community 54"
Cohesion: 1.0
Nodes (1): Final Success Criteria (Section 40)

## Ambiguous Edges - Review These
- `README Hackathon Scope (MVP/Stretch)` → `Core Design Principle: Immersive`  [AMBIGUOUS]
  docs/Morph_Design_Spec.md · relation: conceptually_related_to
- `Immersive Landing Page Concept` → `24-Hour Build Plan Phases`  [AMBIGUOUS]
  docs/Morph_Design_Spec.md · relation: conceptually_related_to

## Knowledge Gaps
- **101 isolated node(s):** `Morph: reproduce environment conditions and isolate the cause of failures.`, `User-space TCP proxy: cross-platform network latency and packet-loss simulation.`, `Actual bound listen port (resolved after start() when listen_port=0).`, `Relay chunks from reader to writer, injecting latency and packet loss.`, `Runnable check: latency is observable, and 100% loss actually blocks delivery.` (+96 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Community 18`** (2 nodes): `Morph: reproduce environment conditions and isolate the cause of failures.`, `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 19`** (2 nodes): `Delta Debugging for CPS with Flaky Test Executions (arXiv 2607.25695)`, `Prior Art and What's Actually New`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 20`** (2 nodes): `Demo Failure Corpus (demo_apps/)`, `Demo Failure Corpus A-D`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 21`** (2 nodes): `What Morph Actually Reproduces (Targeted vs Not Claimed)`, `README Limitations Section`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 22`** (2 nodes): `Recommended Stack Decision Rationale (Section 23)`, `Python Whole-Runtime Stack Decision`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 23`** (2 nodes): `Statistical Comparison Module (comparison.py)`, `compare_failure_rates() Implementation`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 24`** (2 nodes): `Threshold Search Module (threshold.py)`, `search_threshold() Implementation`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 25`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 26`** (1 nodes): `Actual bound listen port (resolved after start() when listen_port=0).`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 27`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 28`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 29`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 30`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 31`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 32`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 33`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 34`** (1 nodes): `Failure A: Simple Timeout`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 35`** (1 nodes): `Failure C: CPU Constraint Race Condition`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 36`** (1 nodes): `Failure D: Locale Date Formatting`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 37`** (1 nodes): `The Problem: It Works On My Machine`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 38`** (1 nodes): `Environment-Triggered Failure`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 39`** (1 nodes): `Architecture Core Loop`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 40`** (1 nodes): `RegressionArtifact Schema`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 41`** (1 nodes): `Error Handling Rules`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 42`** (1 nodes): `Security and Privacy Section`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 43`** (1 nodes): `Signature Interaction: Enter Environment`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 44`** (1 nodes): `OS-Adaptive Workspace`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 45`** (1 nodes): `Color System`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 46`** (1 nodes): `Typography System`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 47`** (1 nodes): `Regression Test Creation Flow`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 48`** (1 nodes): `Hackathon Context and Timeline`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 49`** (1 nodes): `Team and Ownership (Adith/Parth/Sarthak/Rishita)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 50`** (1 nodes): `Product Scope: Pre/Post-Deployment`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 51`** (1 nodes): `CI Requirements (Section 22)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 52`** (1 nodes): `Hard Cuts List (Section 36)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 53`** (1 nodes): `Review 1 Triage Cut Order (Section 38)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 54`** (1 nodes): `Final Success Criteria (Section 40)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **What is the exact relationship between `README Hackathon Scope (MVP/Stretch)` and `Core Design Principle: Immersive`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **What is the exact relationship between `Immersive Landing Page Concept` and `24-Hour Build Plan Phases`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **Why does `run_with_telemetry()` connect `Community 3` to `Community 8`, `Community 0`, `Community 5`, `Community 7`?**
  _High betweenness centrality (0.148) - this node is a cross-community bridge._
- **Why does `RunResult` connect `Community 0` to `Community 1`, `Community 3`, `Community 13`, `Community 7`?**
  _High betweenness centrality (0.124) - this node is a cross-community bridge._
- **Why does `TrialBatch` connect `Community 0` to `Community 1`?**
  _High betweenness centrality (0.071) - this node is a cross-community bridge._
- **Are the 18 inferred relationships involving `run_with_telemetry()` (e.g. with `execute_command()` and `.start()`) actually correct?**
  _`run_with_telemetry()` has 18 INFERRED edges - model-reasoned connections that need verification._
- **Are the 19 inferred relationships involving `TrialBatch` (e.g. with `ComparisonResult` and `ThresholdResult`) actually correct?**
  _`TrialBatch` has 19 INFERRED edges - model-reasoned connections that need verification._