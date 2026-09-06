# Graph Report - .  (2026-09-06)

## Corpus Check
- Corpus is ~19,189 words - fits in a single context window. You may not need a graph.

## Summary
- 269 nodes · 330 edges · 45 communities detected
- Extraction: 58% EXTRACTED · 41% INFERRED · 1% AMBIGUOUS · INFERRED: 136 edges (avg confidence: 0.69)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- [[_COMMUNITY_Causal Classifier and Comparison Schemas|Causal Classifier and Comparison Schemas]]
- [[_COMMUNITY_Profiler Capture Pipeline|Profiler Capture Pipeline]]
- [[_COMMUNITY_OS Adapters and APICLI Surface (Spec)|OS Adapters and API/CLI Surface (Spec)]]
- [[_COMMUNITY_Immersive UI and Cloud Fallback (Spec)|Immersive UI and Cloud Fallback (Spec)]]
- [[_COMMUNITY_Async TCP Proxy (Network Simulation)|Async TCP Proxy (Network Simulation)]]
- [[_COMMUNITY_Experiment Engine and Runtime Controller (Spec)|Experiment Engine and Runtime Controller (Spec)]]
- [[_COMMUNITY_Experiment Engine and Demo Failure Corpus (Spec)|Experiment Engine and Demo Failure Corpus (Spec)]]
- [[_COMMUNITY_Fisher Exact Comparison Module|Fisher Exact Comparison Module]]
- [[_COMMUNITY_Environment-Caused vs Exposed Classification|Environment-Caused vs Exposed Classification]]
- [[_COMMUNITY_Unbuilt Surfaces API, CLI, Frontend, Regression (Spec)|Unbuilt Surfaces: API, CLI, Frontend, Regression (Spec)]]
- [[_COMMUNITY_Environment Profile Schema (Spec and Implementation)|Environment Profile Schema (Spec and Implementation)]]
- [[_COMMUNITY_Proxy Adapter and OS Workspace Spec|Proxy Adapter and OS Workspace Spec]]
- [[_COMMUNITY_System Overview and Core Loop|System Overview and Core Loop]]
- [[_COMMUNITY_Profiler Module (Implementation)|Profiler Module (Implementation)]]
- [[_COMMUNITY_Project Structure Docs|Project Structure Docs]]
- [[_COMMUNITY_Build Plan and Design Priority|Build Plan and Design Priority]]
- [[_COMMUNITY_Package Root|Package Root]]
- [[_COMMUNITY_Reproduction Limitations|Reproduction Limitations]]
- [[_COMMUNITY_Prior Art|Prior Art]]
- [[_COMMUNITY_Python Stack Decision|Python Stack Decision]]
- [[_COMMUNITY_Demo Failure Corpus|Demo Failure Corpus]]
- [[_COMMUNITY_Comparison Module (Implementation)|Comparison Module (Implementation)]]
- [[_COMMUNITY_Threshold Search Module (Implementation)|Threshold Search Module (Implementation)]]
- [[_COMMUNITY_Community 23|Community 23]]
- [[_COMMUNITY_Community 24|Community 24]]
- [[_COMMUNITY_Community 25|Community 25]]
- [[_COMMUNITY_Community 30|Community 30]]
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

## God Nodes (most connected - your core abstractions)
1. `TrialBatch` - 19 edges
2. `ProfileField` - 12 edges
3. `ComparisonResult` - 10 edges
4. `ExperimentResult` - 10 edges
5. `Experiment Engine` - 9 edges
6. `capture_environment()` - 9 edges
7. `ProxyServer` - 9 edges
8. `Morph Core Platform` - 8 edges
9. `classify_failure()` - 8 edges
10. `compare_failure_rates()` - 8 edges

## Surprising Connections (you probably didn't know these)
- `Not Yet Done (Out of Scope This Pass)` --semantically_similar_to--> `Stretch Features List (Section 37)`  [INFERRED] [semantically similar]
  PROGRESS.md → docs/Morph_PRD.md
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

### Community 0 - "Causal Classifier and Comparison Schemas"
Cohesion: 0.09
Nodes (37): BaseModel, classify_failure(), Causal classification: distinguishes an application bug from a failure that is g, application_internal: baseline already fails often, regardless of environment., ComparisonResult, ThresholdResult, compare_batches(), detect_interaction() (+29 more)

### Community 1 - "Profiler Capture Pipeline"
Cohesion: 0.09
Nodes (33): capture_environment(), Capture orchestrator: runs all collectors and assembles an EnvironmentProfile., Collects the current machine's environment into a structured profile., collect_cpu(), CPU collector: architecture, core counts, clock speed., collect_filesystem(), Filesystem collector: detects case sensitivity by probing a temp directory., collect_locale() (+25 more)

### Community 2 - "OS Adapters and API/CLI Surface (Spec)"
Cohesion: 0.12
Nodes (17): Linux Adapter (tc/netem/cgroups), macOS Adapter (dnctl/pfctl), Windows Adapter (Clumsy/JobObjects), BaseAdapter Interface, Typer CLI Interface, EnvironmentProfile Schema, Environment Twin, FastAPI API Server (+9 more)

### Community 3 - "Immersive UI and Cloud Fallback (Spec)"
Cohesion: 0.12
Nodes (17): Cloud Fallback Architecture, Core Design Principle: Immersive, Linux Workspace (P2 Simplified/Recorded Fallback), Platform Priority Rationale (Windows/macOS P0, Linux P2), Cloud Fallback Requirements (Section 25), Dashboard Spec (Section 27), The One Thing Judges Need to Believe (Section 39), Judging Criteria Mapping Table (+9 more)

### Community 4 - "Async TCP Proxy (Network Simulation)"
Cohesion: 0.19
Nodes (5): ProxyServer, User-space TCP proxy: cross-platform network latency and packet-loss simulation., Relay chunks from reader to writer, injecting latency and packet loss., Runnable check: latency is observable, and 100% loss actually blocks delivery., _self_check()

### Community 5 - "Experiment Engine and Runtime Controller (Spec)"
Cohesion: 0.15
Nodes (14): Experiment Engine (morph/engine/), Runtime Controller (morph/runtime/), Telemetry Collector (morph/telemetry/), Experiment Screen Design, Root Cause View Design, Correlation vs Causation (Section 17), Experiment Engine Description (Section 15), Experiment Pseudocode (Section 16) (+6 more)

### Community 6 - "Experiment Engine and Demo Failure Corpus (Spec)"
Cohesion: 0.17
Nodes (13): Baseline vs Treatment Runner, Causal Isolation Engine, CI Invariant Exporter, ElevenLabs Voice Announcer, Experiment Engine, Failure B: Lock TTL vs Network (Flagship), Failure Classifier (Caused vs Exposed), Fisher Exact & Two-Proportion Test (+5 more)

### Community 7 - "Fisher Exact Comparison Module"
Cohesion: 0.21
Nodes (8): compare_failure_rates(), Statistical comparison results: baseline vs. treatment, and threshold search., Tests for morph.engine.comparison: Fisher exact test wrapper., test_failure_rate_properties(), test_identical_rates_are_not_significant(), test_large_decrease_is_significant_decrease(), test_large_increase_is_significant_increase(), test_small_noisy_difference_is_not_significant()

### Community 8 - "Environment-Caused vs Exposed Classification"
Cohesion: 0.17
Nodes (12): Failure Classification (classifier.py, Section 5.3), CAUSED vs EXPOSED vs INCONCLUSIVE UI States, Environment-Caused vs Environment-Exposed (Section 18), Bug Fix: classify_failure Ignored treatment Param, classify_failure() Implementation, Fixed .gitignore Blocking /morph, Status: COMPLETE (25/25 Tests, Ruff Clean), Test Suite (25 Tests: profiler/engine/comparison) (+4 more)

### Community 9 - "Unbuilt Surfaces: API, CLI, Frontend, Regression (Spec)"
Cohesion: 0.22
Nodes (9): API Server and Endpoints (morph/api/), CLI Interface (morph/cli/), Frontend Architecture (frontend/), Regression Artifacts (morph/regression/), Regression Artifact Format (Section 21), Stretch Features List (Section 37), Not Yet Done (Out of Scope This Pass), Local API Dependencies (fastapi, uvicorn, pydantic) (+1 more)

### Community 10 - "Environment Profile Schema (Spec and Implementation)"
Cohesion: 0.25
Nodes (8): compare_profiles() Field Status Logic, TrialBatch/ComparisonResult/ExperimentResult Schema, EnvironmentProfile Schema, RunResult Schema, Environment Profile JSON Format (PRD), Fixed locale_info.py to Use BCP-47 Tags on Windows, Fixed os_info.py to Use distro Instead of Kernel Version, morph/schema/ Minimal Dependency Layer

### Community 11 - "Proxy Adapter and OS Workspace Spec"
Cohesion: 0.29
Nodes (7): BaseAdapter Interface, User-Space TCP Proxy Adapter (adapters/proxy.py), macOS Workspace (P0 Full Craft), Windows Workspace (P0 Full Craft), OS Implementation: Linux/Windows/macOS, ProxyServer Implementation (proxy.py), Why Network Conditions Specifically

### Community 12 - "System Overview and Core Loop"
Cohesion: 0.4
Nodes (5): Morph System Overview, PRD Architecture Diagram, PRD Purpose and Core Loop, README Architecture Diagram, Capture-Reproduce-Run-Experiment-Isolate Loop

### Community 13 - "Profiler Module (Implementation)"
Cohesion: 0.5
Nodes (4): Profiler Module (morph/profiler/), capture.py Orchestrator, Built Profiler Collectors (cpu/memory/os/locale/filesystem), Profiler Dependencies (psutil, py-cpuinfo, distro, tzdata)

### Community 14 - "Project Structure Docs"
Cohesion: 0.67
Nodes (3): Directory Structure Spec, Module Inventory Table, PROGRESS Task Scope (This Pass)

### Community 15 - "Build Plan and Design Priority"
Cohesion: 0.67
Nodes (3): Design Priority Order (Shell to Landing Page), Immersive Landing Page Concept, 24-Hour Build Plan Phases

### Community 16 - "Package Root"
Cohesion: 1.0
Nodes (1): Morph: reproduce environment conditions and isolate the cause of failures.

### Community 17 - "Reproduction Limitations"
Cohesion: 1.0
Nodes (2): What Morph Actually Reproduces (Targeted vs Not Claimed), README Limitations Section

### Community 18 - "Prior Art"
Cohesion: 1.0
Nodes (2): Delta Debugging for CPS with Flaky Test Executions (arXiv 2607.25695), Prior Art and What's Actually New

### Community 19 - "Python Stack Decision"
Cohesion: 1.0
Nodes (2): Recommended Stack Decision Rationale (Section 23), Python Whole-Runtime Stack Decision

### Community 20 - "Demo Failure Corpus"
Cohesion: 1.0
Nodes (2): Demo Failure Corpus (demo_apps/), Demo Failure Corpus A-D

### Community 21 - "Comparison Module (Implementation)"
Cohesion: 1.0
Nodes (2): Statistical Comparison Module (comparison.py), compare_failure_rates() Implementation

### Community 22 - "Threshold Search Module (Implementation)"
Cohesion: 1.0
Nodes (2): Threshold Search Module (threshold.py), search_threshold() Implementation

### Community 23 - "Community 23"
Cohesion: 1.0
Nodes (1): Failure A: Simple Timeout

### Community 24 - "Community 24"
Cohesion: 1.0
Nodes (1): Failure C: CPU Constraint Race Condition

### Community 25 - "Community 25"
Cohesion: 1.0
Nodes (1): Failure D: Locale Date Formatting

### Community 30 - "Community 30"
Cohesion: 1.0
Nodes (1): Actual bound listen port (resolved after start() when listen_port=0).

### Community 34 - "Community 34"
Cohesion: 1.0
Nodes (1): The Problem: It Works On My Machine

### Community 35 - "Community 35"
Cohesion: 1.0
Nodes (1): Environment-Triggered Failure

### Community 36 - "Community 36"
Cohesion: 1.0
Nodes (1): Architecture Core Loop

### Community 37 - "Community 37"
Cohesion: 1.0
Nodes (1): RegressionArtifact Schema

### Community 38 - "Community 38"
Cohesion: 1.0
Nodes (1): Error Handling Rules

### Community 39 - "Community 39"
Cohesion: 1.0
Nodes (1): Security and Privacy Section

### Community 40 - "Community 40"
Cohesion: 1.0
Nodes (1): Signature Interaction: Enter Environment

### Community 41 - "Community 41"
Cohesion: 1.0
Nodes (1): OS-Adaptive Workspace

### Community 42 - "Community 42"
Cohesion: 1.0
Nodes (1): Color System

### Community 43 - "Community 43"
Cohesion: 1.0
Nodes (1): Typography System

### Community 44 - "Community 44"
Cohesion: 1.0
Nodes (1): Regression Test Creation Flow

### Community 45 - "Community 45"
Cohesion: 1.0
Nodes (1): Hackathon Context and Timeline

### Community 46 - "Community 46"
Cohesion: 1.0
Nodes (1): Team and Ownership (Adith/Parth/Sarthak/Rishita)

### Community 47 - "Community 47"
Cohesion: 1.0
Nodes (1): Product Scope: Pre/Post-Deployment

### Community 48 - "Community 48"
Cohesion: 1.0
Nodes (1): CI Requirements (Section 22)

### Community 49 - "Community 49"
Cohesion: 1.0
Nodes (1): Hard Cuts List (Section 36)

### Community 50 - "Community 50"
Cohesion: 1.0
Nodes (1): Review 1 Triage Cut Order (Section 38)

### Community 51 - "Community 51"
Cohesion: 1.0
Nodes (1): Final Success Criteria (Section 40)

## Ambiguous Edges - Review These
- `README Hackathon Scope (MVP/Stretch)` → `Core Design Principle: Immersive`  [AMBIGUOUS]
  docs/Morph_Design_Spec.md · relation: conceptually_related_to
- `Immersive Landing Page Concept` → `24-Hour Build Plan Phases`  [AMBIGUOUS]
  docs/Morph_Design_Spec.md · relation: conceptually_related_to

## Knowledge Gaps
- **99 isolated node(s):** `Environment Twin`, `FieldStatus (Reproduced/Approximated/Unavailable)`, `Windows Adapter (Clumsy/JobObjects)`, `macOS Adapter (dnctl/pfctl)`, `Linux Adapter (tc/netem/cgroups)` (+94 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **Thin community `Package Root`** (2 nodes): `Morph: reproduce environment conditions and isolate the cause of failures.`, `__init__.py`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Reproduction Limitations`** (2 nodes): `What Morph Actually Reproduces (Targeted vs Not Claimed)`, `README Limitations Section`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Prior Art`** (2 nodes): `Delta Debugging for CPS with Flaky Test Executions (arXiv 2607.25695)`, `Prior Art and What's Actually New`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Python Stack Decision`** (2 nodes): `Recommended Stack Decision Rationale (Section 23)`, `Python Whole-Runtime Stack Decision`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Demo Failure Corpus`** (2 nodes): `Demo Failure Corpus (demo_apps/)`, `Demo Failure Corpus A-D`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Comparison Module (Implementation)`** (2 nodes): `Statistical Comparison Module (comparison.py)`, `compare_failure_rates() Implementation`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Threshold Search Module (Implementation)`** (2 nodes): `Threshold Search Module (threshold.py)`, `search_threshold() Implementation`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 23`** (1 nodes): `Failure A: Simple Timeout`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 24`** (1 nodes): `Failure C: CPU Constraint Race Condition`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 25`** (1 nodes): `Failure D: Locale Date Formatting`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 30`** (1 nodes): `Actual bound listen port (resolved after start() when listen_port=0).`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 34`** (1 nodes): `The Problem: It Works On My Machine`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 35`** (1 nodes): `Environment-Triggered Failure`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 36`** (1 nodes): `Architecture Core Loop`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 37`** (1 nodes): `RegressionArtifact Schema`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 38`** (1 nodes): `Error Handling Rules`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 39`** (1 nodes): `Security and Privacy Section`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 40`** (1 nodes): `Signature Interaction: Enter Environment`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 41`** (1 nodes): `OS-Adaptive Workspace`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 42`** (1 nodes): `Color System`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 43`** (1 nodes): `Typography System`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 44`** (1 nodes): `Regression Test Creation Flow`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 45`** (1 nodes): `Hackathon Context and Timeline`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 46`** (1 nodes): `Team and Ownership (Adith/Parth/Sarthak/Rishita)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 47`** (1 nodes): `Product Scope: Pre/Post-Deployment`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 48`** (1 nodes): `CI Requirements (Section 22)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 49`** (1 nodes): `Hard Cuts List (Section 36)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 50`** (1 nodes): `Review 1 Triage Cut Order (Section 38)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.
- **Thin community `Community 51`** (1 nodes): `Final Success Criteria (Section 40)`
  Too small to be a meaningful cluster - may be noise or needs more connections extracted.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **What is the exact relationship between `README Hackathon Scope (MVP/Stretch)` and `Core Design Principle: Immersive`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **What is the exact relationship between `Immersive Landing Page Concept` and `24-Hour Build Plan Phases`?**
  _Edge tagged AMBIGUOUS (relation: conceptually_related_to) - confidence is low._
- **Why does `ComparisonResult` connect `Causal Classifier and Comparison Schemas` to `Fisher Exact Comparison Module`?**
  _High betweenness centrality (0.029) - this node is a cross-community bridge._
- **Why does `ProfileField` connect `Profiler Capture Pipeline` to `Causal Classifier and Comparison Schemas`?**
  _High betweenness centrality (0.027) - this node is a cross-community bridge._
- **Are the 17 inferred relationships involving `TrialBatch` (e.g. with `Causal classification: distinguishes an application bug from a failure that is g` and `application_internal: baseline already fails often, regardless of environment.`) actually correct?**
  _`TrialBatch` has 17 INFERRED edges - model-reasoned connections that need verification._
- **Are the 10 inferred relationships involving `ProfileField` (e.g. with `collect_cpu()` and `CPU collector: architecture, core counts, clock speed.`) actually correct?**
  _`ProfileField` has 10 INFERRED edges - model-reasoned connections that need verification._
- **Are the 8 inferred relationships involving `ComparisonResult` (e.g. with `compare_failure_rates()` and `Statistical comparison results: baseline vs. treatment, and threshold search.`) actually correct?**
  _`ComparisonResult` has 8 INFERRED edges - model-reasoned connections that need verification._