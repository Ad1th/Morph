# Graph Report - /Users/adith/Documents/Dev/ACTIVE/Morph  (2026-09-06)

## Corpus Check
- 72 files · ~86,137 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 622 nodes · 1133 edges · 65 communities detected
- Extraction: 54% EXTRACTED · 46% INFERRED · 0% AMBIGUOUS · INFERRED: 524 edges (avg confidence: 0.66)
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
- [[_COMMUNITY_Community 55|Community 55]]
- [[_COMMUNITY_Community 56|Community 56]]
- [[_COMMUNITY_Community 57|Community 57]]
- [[_COMMUNITY_Community 58|Community 58]]
- [[_COMMUNITY_Community 59|Community 59]]
- [[_COMMUNITY_Community 60|Community 60]]
- [[_COMMUNITY_Community 61|Community 61]]
- [[_COMMUNITY_Community 62|Community 62]]
- [[_COMMUNITY_Community 63|Community 63]]
- [[_COMMUNITY_Community 64|Community 64]]

## God Nodes (most connected - your core abstractions)
1. `EnvironmentProfile` - 47 edges
2. `RuntimeController` - 37 edges
3. `ProxyAdapter` - 33 edges
4. `RunResult` - 30 edges
5. `RegressionArtifact` - 29 edges
6. `BaseAdapter` - 27 edges
7. `run_with_telemetry()` - 24 edges
8. `MockAdapter` - 23 edges
9. `ProxyServer` - 22 edges
10. `TrialBatch` - 22 edges

## Surprising Connections (you probably didn't know these)
- `Stretch Features List (Section 37)` --semantically_similar_to--> `Not Yet Done (Out of Scope This Pass)`  [INFERRED] [semantically similar]
  docs/Morph_PRD.md → PROGRESS.md
- `FieldStatus` --uses--> `Tests for morph.profiler: each collector and the capture orchestrator.`  [INFERRED]
  /Users/adith/Documents/Dev/ACTIVE/Morph/morph/schema/profile.py → C:\Users\parth\Desktop\Morph\tests\test_profiler.py
- `EnvironmentProfile` --uses--> `Capture orchestrator: runs all collectors and assembles an EnvironmentProfile.`  [INFERRED]
  /Users/adith/Documents/Dev/ACTIVE/Morph/morph/schema/profile.py → C:\Users\parth\Desktop\Morph\morph\profiler\capture.py
- `EnvironmentProfile` --uses--> `Collects the current machine's environment into a structured profile.`  [INFERRED]
  /Users/adith/Documents/Dev/ACTIVE/Morph/morph/schema/profile.py → C:\Users\parth\Desktop\Morph\morph\profiler\capture.py
- `Baseline vs Treatment Comparison` --semantically_similar_to--> `Experiment Engine Description (Section 15)`  [INFERRED] [semantically similar]
  README.md → docs/Morph_PRD.md

## Hyperedges (group relationships)
- **Cross-Platform User-Space Proxy Network Simulation** — architecture_proxy_adapter, prd_os_implementation, progress_proxy_server, readme_network_conditions_rationale [INFERRED 0.75]
- **Environment-Caused vs Environment-Exposed Classification Flow** — architecture_classifier_module, prd_environment_caused_vs_exposed_section18, design_spec_exposed_vs_caused, progress_classifier_module, progress_bug_fix_classify_failure [INFERRED 0.80]
- **Baseline/Treatment Isolation and Interaction Detection Loop** — prd_experiment_pseudocode, architecture_experiment_engine, progress_experiment_module, prd_correlation_vs_causation [INFERRED 0.75]

## Communities

### Community 0 - "Community 0"
Cohesion: 0.05
Nodes (35): ABC, BaseAdapter, ProxyAdapter, BaseAdapter interface and cross-platform ProxyAdapter., Abstract interface for operating system and network environment adapters., Return dictionary of environment variables to inject into target process., Cross-platform fallback adapter using user-space TCP proxy and environment varia, get_default_adapter() (+27 more)

### Community 1 - "Community 1"
Cohesion: 0.05
Nodes (71): delete_regression(), list_regressions(), load_regression(), Flight Recorder artifact management for .morph/ regression bundles., Delete a regression bundle directory., Delete a regression bundle directory., Save a RegressionArtifact as a structured directory bundle under base_dir/regres, Load and reconstruct a RegressionArtifact from a bundle directory or regression (+63 more)

### Community 2 - "Community 2"
Cohesion: 0.06
Nodes (54): classify_failure(), Causal classification: distinguishes an application bug from a failure that is g, application_internal: baseline already fails often, regardless of environment., compare_failure_rates(), ComparisonResult, Statistical comparison results: baseline vs. treatment, and threshold search., ThresholdResult, compare_batches() (+46 more)

### Community 3 - "Community 3"
Cohesion: 0.08
Nodes (36): BaseModel, capture_environment(), Capture orchestrator: runs all collectors and assembles an EnvironmentProfile., Collects the current machine's environment into a structured profile., collect_cpu(), CPU collector: architecture, core counts, clock speed., collect_filesystem(), Filesystem collector: detects case sensitivity by probing a temp directory. (+28 more)

### Community 4 - "Community 4"
Cohesion: 0.05
Nodes (43): Failure Classification (classifier.py, Section 5.3), Cloud Fallback Architecture, Experiment Engine (morph/engine/), Runtime Controller (morph/runtime/), Telemetry Collector (morph/telemetry/), Experiment Screen Design, CAUSED vs EXPOSED vs INCONCLUSIVE UI States, Core Design Principle: Immersive (+35 more)

### Community 5 - "Community 5"
Cohesion: 0.08
Nodes (34): Self-check for Failure C. Confirms the app still fails the way we think it does., A calm CPU must hide the race, or there is no baseline to compare against., Baseline fail rate must stay under 5% or the experiment engine has no signal., de_DE is the baseline: it must never fail, on any run., Frequent preemption must expose the race at the doc's 30-60% rate., With the response pushed past the deadline, the failure must be near-total., en_US is the condition: it must always fail, on any run., The lock must hold under the exact condition that breaks the app. (+26 more)

### Community 6 - "Community 6"
Cohesion: 0.07
Nodes (30): Linux Adapter (tc/netem/cgroups), macOS Adapter (dnctl/pfctl), Windows Adapter (Clumsy/JobObjects), BaseAdapter Interface, Baseline vs Treatment Runner, Causal Isolation Engine, CI Invariant Exporter, Typer CLI Interface (+22 more)

### Community 7 - "Community 7"
Cohesion: 0.14
Nodes (24): _early_result(), _kill_tree(), _monitor(), _new_run_id(), _now_iso(), Spawn a subprocess, capture output, track peak RSS + duration, kill cleanly on t, Run `command`, returning a populated RunResult.      `env`, if given, is passed, Terminate the process and every descendant; escalate to SIGKILL after a grace pe (+16 more)

### Community 8 - "Community 8"
Cohesion: 0.1
Nodes (21): _apply_locale(), _base_name(), _candidates(), create_app(), _env_requested(), _Handler, main(), _parse_buggy() (+13 more)

### Community 9 - "Community 9"
Cohesion: 0.12
Nodes (11): Apply network conditions (latency, packet loss, bandwidth limit)., Apply CPU core count or throttle restrictions., Apply memory restrictions., Apply locale and timezone settings., Clean up all applied conditions and restore normal host state., Return capabilities dict: {'network': bool, 'cpu': bool, 'memory': bool, 'locale, ProxyServer, User-space TCP proxy: cross-platform network latency and packet-loss simulation. (+3 more)

### Community 10 - "Community 10"
Cohesion: 0.22
Nodes (19): extract_error_message(), extract_error_type(), extract_stack_trace(), _iter_sources(), _match(), Best-effort extraction of error type / message / stack trace from process output, Return the match that best identifies the failure in `text`.      Java header fi, test_bare_type_colon_message() (+11 more)

### Community 11 - "Community 11"
Cohesion: 0.3
Nodes (13): execute_command(), Thin dispatch layer: merge env overrides onto os.environ, then run with telemetr, Execute `command` under a copy of the current environment plus `env_overrides`., _py(), test_cwd_propagates(), test_error_parsing_propagates(), test_merges_with_os_environ(), test_no_overrides_still_inherits_environ() (+5 more)

### Community 12 - "Community 12"
Cohesion: 0.32
Nodes (5): BaseAdapter, DummyAdapter, test_base_adapter_context_manager(), test_base_adapter_contract(), test_proxy_adapter_capabilities_and_locale()

### Community 13 - "Community 13"
Cohesion: 0.22
Nodes (9): API Server and Endpoints (morph/api/), CLI Interface (morph/cli/), Frontend Architecture (frontend/), Regression Artifacts (morph/regression/), Regression Artifact Format (Section 21), Stretch Features List (Section 37), Not Yet Done (Out of Scope This Pass), Local API Dependencies (fastapi, uvicorn, pydantic) (+1 more)

### Community 14 - "Community 14"
Cohesion: 0.25
Nodes (8): compare_profiles() Field Status Logic, TrialBatch/ComparisonResult/ExperimentResult Schema, EnvironmentProfile Schema, RunResult Schema, Environment Profile JSON Format (PRD), Fixed locale_info.py to Use BCP-47 Tags on Windows, Fixed os_info.py to Use distro Instead of Kernel Version, morph/schema/ Minimal Dependency Layer

### Community 15 - "Community 15"
Cohesion: 0.29
Nodes (7): BaseAdapter Interface, User-Space TCP Proxy Adapter (adapters/proxy.py), macOS Workspace (P0 Full Craft), Windows Workspace (P0 Full Craft), OS Implementation: Linux/Windows/macOS, ProxyServer Implementation (proxy.py), Why Network Conditions Specifically

### Community 16 - "Community 16"
Cohesion: 0.4
Nodes (5): Morph System Overview, PRD Architecture Diagram, PRD Purpose and Core Loop, README Architecture Diagram, Capture-Reproduce-Run-Experiment-Isolate Loop

### Community 17 - "Community 17"
Cohesion: 0.5
Nodes (4): Profiler Module (morph/profiler/), capture.py Orchestrator, Built Profiler Collectors (cpu/memory/os/locale/filesystem), Profiler Dependencies (psutil, py-cpuinfo, distro, tzdata)

### Community 18 - "Community 18"
Cohesion: 0.67
Nodes (3): Directory Structure Spec, Module Inventory Table, PROGRESS Task Scope (This Pass)

### Community 19 - "Community 19"
Cohesion: 0.67
Nodes (3): Design Priority Order (Shell to Landing Page), Immersive Landing Page Concept, 24-Hour Build Plan Phases

### Community 20 - "Community 20"
Cohesion: 1.0
Nodes (1): Morph: reproduce environment conditions and isolate the cause of failures.

### Community 21 - "Community 21"
Cohesion: 1.0
Nodes (2): Delta Debugging for CPS with Flaky Test Executions (arXiv 2607.25695), Prior Art and What's Actually New

### Community 22 - "Community 22"
Cohesion: 1.0
Nodes (2): Recommended Stack Decision Rationale (Section 23), Python Whole-Runtime Stack Decision

### Community 23 - "Community 23"
Cohesion: 1.0
Nodes (2): What Morph Actually Reproduces (Targeted vs Not Claimed), README Limitations Section

### Community 24 - "Community 24"
Cohesion: 1.0
Nodes (2): Demo Failure Corpus (demo_apps/), Demo Failure Corpus A-D

### Community 25 - "Community 25"
Cohesion: 1.0
Nodes (2): Statistical Comparison Module (comparison.py), compare_failure_rates() Implementation

### Community 26 - "Community 26"
Cohesion: 1.0
Nodes (2): Threshold Search Module (threshold.py), search_threshold() Implementation

### Community 27 - "Community 27"
Cohesion: 1.0
Nodes (0): 

### Community 28 - "Community 28"
Cohesion: 1.0
Nodes (1): Actual bound listen port (resolved after start() when listen_port=0).

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
Nodes (0): 

### Community 35 - "Community 35"
Cohesion: 1.0
Nodes (0): 

### Community 36 - "Community 36"
Cohesion: 1.0
Nodes (0): 

### Community 37 - "Community 37"
Cohesion: 1.0
Nodes (0): 

### Community 38 - "Community 38"
Cohesion: 1.0
Nodes (0): 

### Community 39 - "Community 39"
Cohesion: 1.0
Nodes (0): 

### Community 40 - "Community 40"
Cohesion: 1.0
Nodes (0): 

### Community 41 - "Community 41"
Cohesion: 1.0
Nodes (0): 

### Community 42 - "Community 42"
Cohesion: 1.0
Nodes (0): 

### Community 43 - "Community 43"
Cohesion: 1.0
Nodes (0): 

### Community 44 - "Community 44"
Cohesion: 1.0
Nodes (1): Failure A: Simple Timeout

### Community 45 - "Community 45"
Cohesion: 1.0
Nodes (1): Failure C: CPU Constraint Race Condition

### Community 46 - "Community 46"
Cohesion: 1.0
Nodes (1): Failure D: Locale Date Formatting

### Community 47 - "Community 47"
Cohesion: 1.0
Nodes (1): The Problem: It Works On My Machine

### Community 48 - "Community 48"
Cohesion: 1.0
Nodes (1): Environment-Triggered Failure

### Community 49 - "Community 49"
Cohesion: 1.0
Nodes (1): Architecture Core Loop

### Community 50 - "Community 50"
Cohesion: 1.0
Nodes (1): RegressionArtifact Schema

### Community 51 - "Community 51"
Cohesion: 1.0
Nodes (1): Error Handling Rules

### Community 52 - "Community 52"
Cohesion: 1.0
Nodes (1): Security and Privacy Section

### Community 53 - "Community 53"
Cohesion: 1.0
Nodes (1): Signature Interaction: Enter Environment

### Community 54 - "Community 54"
Cohesion: 1.0
Nodes (1): OS-Adaptive Workspace

### Community 55 - "Community 55"
Cohesion: 1.0
Nodes (1): Color System

### Community 56 - "Community 56"
Cohesion: 1.0
Nodes (1): Typography System

### Community 57 - "Community 57"
Cohesion: 1.0
Nodes (1): Regression Test Creation Flow

### Community 58 - "Community 58"
Cohesion: 1.0
Nodes (1): Hackathon Context and Timeline

### Community 59 - "Community 59"
Cohesion: 1.0
Nodes (1): Team and Ownership (Adith/Parth/Sarthak/Rishita)

### Community 60 - "Community 60"
Cohesion: 1.0
Nodes (1): Product Scope: Pre/Post-Deployment

### Community 61 - "Community 61"
Cohesion: 1.0
Nodes (1): CI Requirements (Section 22)

### Community 62 - "Community 62"
Cohesion: 1.0
Nodes (1): Hard Cuts List (Section 36)

### Community 63 - "Community 63"
Cohesion: 1.0
Nodes (1): Review 1 Triage Cut Order (Section 38)

### Community 64 - "Community 64"
Cohesion: 1.0
Nodes (1): Final Success Criteria (Section 40)

## Ambiguous Edges - Review These
- `README Hackathon Scope (MVP/Stretch)` → `Core Design Principle: Immersive`  [AMBIGUOUS]
  docs/Morph_Design_Spec.md · relation: conceptually_related_to
- `Immersive Landing Page Concept` → `24-Hour Build Plan Phases`  [AMBIGUOUS]
  docs/Morph_Design_Spec.md · relation: conceptually_related_to

## Knowledge Gaps
- **133 isolated node(s):** `Morph: reproduce environment conditions and isolate the cause of failures.`, `User-space TCP proxy: cross-platform network latency and packet-loss simulation.`, `Actual bound listen port (resolved after start() when listen_port=0).`, `Relay chunks from reader to writer, injecting latency and packet loss.`, `Runnable check: latency is observable, and 100% loss actually blocks delivery.` (+128 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Community 20`** (2 nodes): `Morph: reproduce environment conditions and isolate the cause of failures.`, `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 21`** (2 nodes): `Delta Debugging for CPS with Flaky Test Executions (arXiv 2607.25695)`, `Prior Art and What's Actually New`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 22`** (2 nodes): `Recommended Stack Decision Rationale (Section 23)`, `Python Whole-Runtime Stack Decision`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 23`** (2 nodes): `What Morph Actually Reproduces (Targeted vs Not Claimed)`, `README Limitations Section`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 24`** (2 nodes): `Demo Failure Corpus (demo_apps/)`, `Demo Failure Corpus A-D`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 25`** (2 nodes): `Statistical Comparison Module (comparison.py)`, `compare_failure_rates() Implementation`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 26`** (2 nodes): `Threshold Search Module (threshold.py)`, `search_threshold() Implementation`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 27`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 28`** (1 nodes): `Actual bound listen port (resolved after start() when listen_port=0).`
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
- **Thin community `Community 34`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 35`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 36`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 37`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 38`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 39`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 40`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 41`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 42`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 43`** (1 nodes): `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 44`** (1 nodes): `Failure A: Simple Timeout`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 45`** (1 nodes): `Failure C: CPU Constraint Race Condition`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 46`** (1 nodes): `Failure D: Locale Date Formatting`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 47`** (1 nodes): `The Problem: It Works On My Machine`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 48`** (1 nodes): `Environment-Triggered Failure`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 49`** (1 nodes): `Architecture Core Loop`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 50`** (1 nodes): `RegressionArtifact Schema`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 51`** (1 nodes): `Error Handling Rules`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 52`** (1 nodes): `Security and Privacy Section`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 53`** (1 nodes): `Signature Interaction: Enter Environment`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 54`** (1 nodes): `OS-Adaptive Workspace`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 55`** (1 nodes): `Color System`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 56`** (1 nodes): `Typography System`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 57`** (1 nodes): `Regression Test Creation Flow`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 58`** (1 nodes): `Hackathon Context and Timeline`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 59`** (1 nodes): `Team and Ownership (Adith/Parth/Sarthak/Rishita)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 60`** (1 nodes): `Product Scope: Pre/Post-Deployment`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 61`** (1 nodes): `CI Requirements (Section 22)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 62`** (1 nodes): `Hard Cuts List (Section 36)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 63`** (1 nodes): `Review 1 Triage Cut Order (Section 38)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 64`** (1 nodes): `Final Success Criteria (Section 40)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **What is the exact relationship between `README Hackathon Scope (MVP/Stretch)` and `Core Design Principle: Immersive`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **What is the exact relationship between `Immersive Landing Page Concept` and `24-Hour Build Plan Phases`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **Why does `RunResult` connect `Community 0` to `Community 1`, `Community 2`, `Community 3`, `Community 7`, `Community 11`?**
  _High betweenness centrality (0.129) - this node is a cross-community bridge._
- **Why does `EnvironmentProfile` connect `Community 1` to `Community 0`, `Community 2`, `Community 3`?**
  _High betweenness centrality (0.119) - this node is a cross-community bridge._
- **Why does `run_with_telemetry()` connect `Community 7` to `Community 0`, `Community 9`, `Community 10`, `Community 11`?**
  _High betweenness centrality (0.117) - this node is a cross-community bridge._
- **Are the 45 inferred relationships involving `EnvironmentProfile` (e.g. with `RuntimeController` and `Runtime Controller: orchestrates environment condition reproduction and executio`) actually correct?**
  _`EnvironmentProfile` has 45 INFERRED edges - model-reasoned connections that need verification._
- **Are the 32 inferred relationships involving `RuntimeController` (e.g. with `BaseAdapter` and `ProxyAdapter`) actually correct?**
  _`RuntimeController` has 32 INFERRED edges - model-reasoned connections that need verification._