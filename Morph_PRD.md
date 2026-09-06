# Morph — Product Requirements Document

> **Test your software in environments you don't physically have.**

## 1. Purpose

Morph is a local-first developer tool for reproducing application-relevant environments and finding which environmental conditions are responsible for software failures.

The hackathon prototype must prove this loop end to end:

**capture/define → reproduce → run → observe failure → vary conditions → isolate cause → fix → replay → pass**

This PRD extends the existing Morph README and keeps its positioning, terminology, architecture direction, limitations, and demo narrative as the source of truth.

---

## 2. Hackathon context

- Organizer: ACM VIT
- Start: **6 September, 3:00 PM IST**
- Review 1: **7 September, 1:00 AM–5:00 AM IST**
- Hack resumes: **7 September, 8:00 AM–7:00 PM IST**
- Review 2 preparation: **9:00 PM–12:00 AM IST**
- Review 2: **1:00 AM–5:00 AM IST**
- Finals: **9:00 AM–3:00 PM IST**

### Strategy

The core product should be demonstrable by Review 1. After that, prioritize reliability, stronger experiments, integrations, UI polish, demo hardening, and pitching.

The README's intended live story is already:

**Detect → reproduce → diagnose → fix → verify.**

### Judging criteria mapping

ACM VIT judges on: Innovation, relevance to the problem, technical complexity, implementation, functionality, UI/UX, scalability, future scope, and presentation. Each phase and feature in this PRD should be traceable to at least one of these — use this table during pitch prep (Section 34) to make sure the story actually hits every criterion instead of over-indexing on the demo alone.

| Criterion | Where it's earned |
|---|---|
| Innovation | The experiment engine (Sections 15–18): causal isolation over real machine/network conditions, not just environment fingerprinting. Cite the prior-art distinction from the README explicitly here. |
| Relevance | Section 1's problem framing — "works on my machine" is universal across every judge's own experience. |
| Technical complexity | Sections 16–17 (statistical comparison, interaction-effect detection), Section 11 (OS-native network/resource shaping across three platforms). |
| Implementation | The MVP table (Section 6) and the fact that P0 items are stated as "must work live," not aspirational. |
| Functionality | Section 39's live-proof sequence — a judge watching it end to end. |
| UI/UX | Section 27 dashboard — the REPRODUCED/APPROXIMATED/UNAVAILABLE field-level honesty is itself a UX/trust feature worth calling out explicitly, not just a visual. |
| Scalability | Section 25 (cloud fallback routing) and Section 20 (production-feedback loop) — this is designed to extend past a single laptop. |
| Future scope | Section 26 sponsor integrations plus Section 37 stretch list — frame as "here's the roadmap," not "here's what we ran out of time for." |
| Presentation | Section 39 script + confirmed pitch time box (flagged in Section 34). |

---

# 3. Team and ownership

## Adith

**Primary:** backend architecture, system design, runtime, Raspberry Pi/Linux, integration.

Initial tasks:
- define profile schema
- define runtime/OS-adapter interfaces
- build execution and telemetry pipeline
- implement Linux controls on the Pi
- integrate the main components

## Parth

**Primary:** profiler, experiment engine, testing, network manipulation, causal isolation.

Initial tasks:
- build environment profiler
- implement baseline/treatment loop
- implement network experiments
- create deterministic failure corpus
- implement result scoring and threshold search

## Sarthak

**Primary:** frontend, API integration, CI, full-stack integration.

Initial tasks:
- frontend shell
- local API
- environment/profile screens
- run/experiment screens
- CI checks
- connect frontend to real backend output

## Rishita

**Primary:** product design, visual system, dashboard UX, landing page, demo presentation.

Initial tasks:
- dashboard information architecture
- reproduction/failure screen first
- environment-difference visualizations
- landing-page concept
- demo visual flow

---

# 4. Product scope

Morph has two entry points.

### Pre-deployment

A developer defines a target environment, such as:

```text
Windows 11
4 CPU cores
8 GB RAM
en-IN
Asia/Kolkata
180 ms latency
2% packet loss
```

Morph recreates the controllable parts and runs the application there.

### Post-deployment

A lightweight profiler captures a user's relevant environment together with an application failure/log. The developer imports that capture and Morph attempts to reproduce it.

Once the cause is identified and fixed, the same environment can become a regression test.

The README explicitly defines this production-feedback path and the resulting regression workflow.

---

# 5. What Morph actually reproduces

Morph does **not** claim to emulate an entire physical computer.

It reproduces application-facing conditions that can be controlled or approximated.

### Targeted

- OS family/version
- CPU architecture
- CPU availability/core count
- CPU resource limits
- RAM limits where supported
- locale
- timezone
- selected filesystem behaviour
- network latency
- packet loss
- bandwidth where supported
- process environment
- application dependencies
- application inputs
- execution conditions

### Not claimed

- perfect physical hardware emulation
- turning 8 GB RAM into physically equivalent 16 GB RAM
- exact CPU clock/thermal behaviour
- exact GPU/driver behaviour
- every kernel/hardware detail
- making macOS literally become Windows

These limitations are intentionally part of the project's technical framing.

If required physical resources do not exist locally, Morph can route the run to a cloud worker instead.

---

# 6. MVP

| Feature | Priority | Requirement |
|---|---:|---|
| Define environment profile | P0 | **Must work live** |
| Capture environment | P0 | **Must work live** |
| Portable JSON profile | P0 | **Must work live** |
| Run application | P0 | **Must work live** |
| Collect telemetry | P0 | **Must work live** |
| Network latency injection | P0 | **Must work live** |
| Packet-loss injection | P0 | **Must work live** |
| CPU limitation | P0 | **Must work live** |
| Environment comparison | P0 | **Must work live** |
| Repeated baseline/treatment runs | P0 | **Must work live** |
| Parameter isolation | P0 | **Must work live** |
| Clear cause/evidence result | P0 | **Must work live** |
| Windows support | P0 | **Must work live** |
| macOS support | P0 | **Must work live** |
| Linux/Pi support | P2 | Recorded fallback acceptable |
| Memory limitation | P1 | Live if stable |
| Locale/timezone | P1 | Live if stable |
| Threshold search | P1 | Live if stable |
| Regression artifact | P1 | Live if stable |
| Production error capture | P1 | Live if stable |
| Cloud worker | P1 | Recorded fallback acceptable |
| Tin integration | P1 | Recorded fallback acceptable |
| n8n integration | P1 | Recorded fallback acceptable |
| SGLang | P2 | Recorded fallback |
| ElevenLabs | P3 | Recorded fallback |

---

# 7. Architecture

```text
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

The profile remains portable while the implementation underneath is OS-specific. The README explicitly avoids claiming that one identical API can control all operating systems in the same way.

---

# 8. Environment profile

Use a versioned JSON format.

Example:

```json
{
  "version": "1.0",
  "os": {
    "family": "windows",
    "version": "11"
  },
  "cpu": {
    "architecture": "x86_64",
    "cores": 4,
    "logical_processors": 4,
    "clock_mhz": 2400
  },
  "memory": {
    "total_mb": 8192
  },
  "locale": {
    "locale": "en-IN",
    "timezone": "Asia/Kolkata"
  },
  "filesystem": {
    "case_sensitive": false
  },
  "network": {
    "latency_ms": 180,
    "packet_loss_percent": 2,
    "bandwidth_mbps": 10
  }
}
```

Each field should also be capable of being marked as:

- captured
- requested
- reproduced
- approximated
- unavailable

That prevents the UI from claiming something was reproduced when it was only requested.

---

# 9. What is captured

Capture only information relevant to reproduction or diagnosis.

## Machine

- OS/version
- CPU architecture
- physical/logical cores
- reported CPU information
- reported clock information
- total/available RAM
- GPU information where useful
- relevant hardware characteristics

Avoid unnecessary personal identifiers.

## Runtime

- language/runtime version
- relevant environment variables
- application version/build ID
- dependency versions where practical
- filesystem characteristics

## Locale

- locale
- timezone
- language
- date/time formatting information where useful

## Network

- measured latency
- packet loss
- bandwidth estimate
- connection information where available
- region/endpoint information where relevant

## Failure context

- exit code
- exception/error type
- stack trace
- application logs
- timestamp
- test/input identifier

The README specifically describes capturing OS, CPU, RAM, locale, filesystem behaviour, network conditions, and failure information as part of the post-deployment flow.

---

# 10. Reproduction: exactly what happens

Suppose the profile says:

```text
4 CPU cores
8 GB RAM
180 ms latency
2% packet loss
en-IN
```

Morph loads the profile and asks the current OS adapter to apply each condition it can reproduce.

Conceptually:

```text
CPU      → restrict process CPU resources
Memory   → apply process/job memory limit where supported
Network  → apply network shaping
Locale   → launch with controlled locale/environment
Timezone → launch with controlled timezone
Files    → run against isolated filesystem/test directory
```

If something cannot be reproduced:

```text
Requested: 16 GB RAM
Local:      8 GB RAM

Result:
NOT_REPRODUCIBLE_LOCALLY
```

Morph should then either skip that property with an explicit warning or route the run to a machine/cloud worker with the required resources.

This is important: Morph should never fake hardware equivalence.

---

# 11. OS implementation

## Linux / Raspberry Pi

Use Linux-native facilities.

Network shaping example:

```bash
sudo tc qdisc add dev eth0 root netem delay 180ms loss 2%
```

Remove:

```bash
sudo tc qdisc del dev eth0 root
```

Use Linux cgroups/resource controls where appropriate for CPU and memory.

The Pi is a headless runtime target, not a GUI target.

## Windows

Use a Windows traffic-shaping utility such as Clumsy or an equivalent mechanism.

The Morph runtime should expose a common operation:

```text
apply_network(latency=180ms, loss=2%)
```

while the Windows adapter handles the OS-specific implementation.

Use Windows-native process/job controls for resource constraints where practical.

## macOS

Use macOS-compatible network shaping facilities/utilities and process resource controls.

macOS is the main development and demo machine.

---

# 12. Raspberry Pi

Available:

- Raspberry Pi 4B
- 4 GB RAM
- 32 GB storage
- Raspberry Pi Lite
- SSH only
- no monitor

Use it for:

- Linux runtime
- CLI
- network experiments
- server/API workloads
- headless demo applications
- runtime validation

Do **not** build GUI testing around the Pi.

UI testing happens on the Mac and Windows machines.

---

# 13. Demo failure corpus

Do not depend on discovering an accidental bug during the hackathon. Build small applications with controlled failures.

## Failure A: timeout

A client calls a server with a deliberately tight timeout.

```text
normal network → PASS
high latency   → FAIL
```

Use for the first reproduction demo.

## Failure B: latency + packet-loss interaction

A client uses retries and a connection pool.

```text
latency alone       → PASS
packet loss alone   → PASS
latency + loss      → FAIL
```

This should be the flagship experiment because it demonstrates that Morph can find combinations rather than simply toggling one setting.

## Failure C: concurrency

A small application contains a race condition whose probability increases under constrained CPU scheduling.

```text
normal CPU → rarely fails
low CPU    → frequently fails
```

This demonstrates an environment-exposed application bug.

## Failure D: locale

A date/number parser makes an incorrect locale assumption.

This demonstrates compatibility testing.

Only A and B are required for Review 1.

---

# 14. Testing the target applications

Morph should support three distinct test modes.

## Unit tests

For deterministic Morph components:

- profile serialization
- validation
- environment diff
- experiment generation
- result aggregation
- threshold calculation
- regression artifacts

## Application test commands

Each demo application should expose a simple command such as:

```bash
./demo-app test
```

Morph runs that same command repeatedly under different conditions.

## Manual QA

Manual testing is reserved for:

- dashboard interaction
- visual environment comparison
- final end-to-end flow
- error handling
- live demo reliability

Do not attempt to automate every GUI interaction in the 24-hour window.

---

# 15. Experiment engine

The experiment engine is the core differentiator.

A single failed run proves very little.

### Baseline

Run the application repeatedly under normal conditions.

```text
100 runs
2 failures
```

### Treatment

Run the exact same application/test with one environmental change.

```text
100 runs
71 failures
```

### Isolation

Repeat this across candidate variables:

```text
CPU constraint             → 3/100
RAM constraint             → 2/100
Locale change              → 2/100
Latency                    → 5/100
Packet loss                → 6/100
Latency + packet loss      → 71/100
```

Then narrow the parameter:

```text
100 ms → PASS
150 ms → PASS
200 ms → FAIL
```

The README already establishes this baseline/treatment and threshold-search model.

---

# 16. Experiment pseudocode

```text
baseline = run_trials(normal_profile, N)

for variable in candidate_variables:

    treatment_profile = change(normal_profile, variable)

    result = run_trials(treatment_profile, N)

    compare(
        baseline.failure_rate,
        result.failure_rate
    )

    if result is meaningfully different:
        mark variable as candidate

for candidate in candidates:

    search its parameter range

    run repeated trials at each point

    locate the smallest region
    where failure probability increases

for important candidates:

    test combinations

return:
    candidate conditions
    failure rates
    thresholds
    interactions
    evidence
```

For the prototype, use a simple statistically defensible comparison. Fisher's exact test is suitable for small binary trial counts; a two-proportion comparison can be used for larger samples.

Do not build a research-grade causal inference framework during the hackathon.

---

# 17. Correlation vs causation

Suppose:

```text
CPU = 2 cores
latency = 200ms
failure = YES
```

Do not conclude that both caused the bug.

Run:

```text
normal CPU + normal network
low CPU    + normal network
normal CPU + bad network
low CPU    + bad network
```

If only the combination produces the failure:

```text
CPU alone       → PASS
network alone   → PASS
CPU + network   → FAIL
```

report an interaction.

If low CPU alone raises the failure rate, CPU is the stronger causal candidate.

The important distinction is controlled intervention rather than simply observing that two things appeared together.

---

# 18. Environment-caused vs environment-exposed

Morph should distinguish:

### Environment-caused

The application is stable under baseline conditions and fails when a particular environmental condition is introduced.

### Environment-exposed

The environment changes timing or scheduling enough to expose an application bug that already exists.

Example:

```text
normal:  1/100 failures
low CPU: 48/100 failures
```

The report should say:

> CPU constraint strongly increases the probability of the existing failure.

It should not automatically say:

> CPU caused the bug.

This distinction is especially important for concurrency bugs.

---

# 19. Root-cause result

The dashboard should produce evidence like:

```text
FAILURE REPRODUCED

Baseline
100 runs
2 failures

Captured environment
100 runs
71 failures

Strongest condition
Latency + packet loss

Threshold
~150–200 ms latency

Latency alone
Not sufficient

Packet loss alone
Not sufficient

Interaction
Confirmed
```

Also show:
- trial count
- failure rate
- relevant logs/error signatures
- parameter values
- unsupported/approximated environment fields
- confidence/statistical result where calculated

Morph's README explicitly emphasizes reporting the actual responsible condition rather than simply saying "bad network."

---

# 20. Post-deployment flow

```text
User application
      ↓
Error/log event
      ↓
Environment profiler
      ↓
Profile + failure context
      ↓
Developer imports capture
      ↓
Morph reproduces failure
      ↓
Controlled experiments
      ↓
Cause / interaction
      ↓
Developer fixes application
      ↓
Replay captured environment
      ↓
PASS
```

The production path and regression conversion are part of the README's intended product loop.

---

# 21. Regression artifact

Store a reproducible case on disk:

```text
.morph/
  regressions/
    timeout-001/
      environment.json
      command.json
      expected.json
      metadata.json
```

Example:

```json
{
  "environment": "environment.json",
  "command": "./demo-app test",
  "expected": {
    "exit_code": 0,
    "failure_rate_max": 0.01
  }
}
```

Replay:

```bash
morph replay .morph/regressions/timeout-001
```

Store:
- environment profile
- application/build identifier
- command
- test/input identifier
- expected outcome
- telemetry thresholds where relevant
- creation metadata
- failure signature

After the fix, the exact same artifact is replayed.

---

# 22. CI

## On push

Run:

```text
Go unit tests
Go formatting
Go lint
TypeScript type checking
ESLint
frontend build
backend build
profile schema validation
CLI smoke test
basic integration test
```

## Pre-merge

Run:
- all unit tests
- integration tests
- deterministic demo applications
- frontend build
- CLI smoke tests
- available cross-platform adapter tests

## Blocking

Block merges for:
- compilation/build failures
- unit-test failures
- schema failures
- broken CLI
- broken core experiment-engine tests
- type/lint failures where configured

## Advisory

Do not block on:
- long reproduction campaigns
- cloud workers
- extended performance tests
- sponsor services

Cloud or sponsor availability must never be required for the core build.

---

# 23. Recommended stack

**Confirm this in Phase 1 before writing code — it is the single highest-leverage decision in the whole plan.** The choice below is the architecturally "correct" one on paper; it is only correct in practice if the team is actually fast in it. Nobody's stated skills (backend/system-design, ML basics, frontend-shifting-to-fullstack) explicitly include Go proficiency. If nobody on the team already writes Go comfortably, do not choose it for the sake of the pitch — nonfamiliarity here costs hours 1–4 to language friction instead of building, in a plan that has no slack for that.

**Decision rule:** whoever owns the runtime (Adith) states their actual comfort level with each option below, out loud, at the start of Phase 1. Pick based on that, not on which one sounds most "systems-y."

## Core runtime — pick one

**Option A: Go** — best fit *if someone already knows it well*.
- strong system/process tooling, straightforward concurrency, single-binary distribution, good cross-platform compilation, suitable CLI

**Option B: Python** — best fit if nobody has real Go experience.
- matches Parth's ML background directly, fastest iteration speed, `subprocess` + shelling out to `tc`/`Clumsy`/network tools works fine for this scope, weaker for a distributable single binary but that doesn't matter for a hackathon demo running from source

**Option C: TypeScript/Node end-to-end** — best fit if minimizing context-switching across a 4-person team matters more than raw systems fit.
- matches Sarthak's trajectory, one language for backend + frontend, still fine for shelling out to OS-native network/resource tools the same way Python would

Whichever is picked, the CI section below assumes Go — swap the toolchain-specific checks (`Go test`, `Go lint`, module cache) for the equivalent in Python (`pytest`, `ruff`/`flake8`, pip cache) or Node (`vitest`/`jest`, `eslint`, npm cache) if a different option is chosen.

## Python

Use only where useful for:
- experiment/statistical scripts
- quick demo applications
- optional SGLang/reporting integration

## Frontend

- React
- TypeScript
- Vite
- existing lightweight component library if useful

## Profile

- versioned JSON

## Local API

- small HTTP API between frontend and controller

## Testing

- Go test
- pytest for Python demo applications
- Playwright only for essential browser smoke tests

---

# 24. Dependency cache

The 1 TB HDD should be used as a practical offline cache, not filled with arbitrary dependencies.

Recommended:

### Go

- Go toolchain
- module cache
- project dependencies

### Node

- Node.js
- npm/pnpm cache
- frontend dependencies

### Python

- Python
- pip wheel cache
- pytest
- only packages actually used by demo applications

### System tools

Keep installers/packages for:
- Git
- Go
- Node
- Python
- network shaping tools
- browser automation dependencies
- required platform utilities

### Realistic size

Approximately **5–15 GB** should be enough for a useful project-specific offline cache.

50–100 GB is unnecessary unless you intentionally decide to cache large optional toolchains or datasets.

---

# 25. Cloud

Cloud is a fallback.

Recommended minimum worker:

- 2–4 vCPU
- 8–16 GB RAM
- 30–50 GB disk
- Linux
- enough network access for required dependencies

Use it for:
- targets larger than local machines
- remote reproduction
- final fallback
- Tin integration

Do not run every experiment in the cloud.

A local machine with 8 GB RAM should not pretend to reproduce a 16 GB machine. If 16 GB is genuinely required, Morph should detect that and route to a suitable worker.

---

# 26. Sponsor integrations

## Tin Computer — core

Use Tin as the remote execution target when local hardware cannot satisfy a profile.

```text
Profile
  ↓
Local capability check
  ↓
Cannot reproduce locally
  ↓
Tin worker
  ↓
Run application
  ↓
Collect telemetry
  ↓
Return result
```

**Failure fallback:** local execution continues; cloud results can be prerecorded for the demo.

## n8n — structural

Use n8n around the workflow:

```text
CI failure
   ↓
n8n
   ↓
Morph reproduction
   ↓
Experiment
   ↓
Result
   ↓
Notification/report
```

n8n must not contain the actual causal-analysis logic.

**Failure fallback:** execute the same workflow directly through Morph.

## SGLang — optional

Use only for turning deterministic experiment output into readable prose.

It must not decide the root cause.

## ElevenLabs — optional

Use only as demo polish for a spoken result.

## Protoflow

Do not force it into a software-only project.

## codecrafters and DevSwarm — excluded

Neither has a clear structural fit for this architecture: codecrafters is a build-your-own-X learning platform, not an infra/runtime dependency, and DevSwarm's fit is unclear from the sponsor list alone. If either turns out to offer something genuinely useful once sponsor tracks are confirmed at the venue, evaluate then — do not force an integration to check a box.

The README already identifies Tin and n8n as structural integrations and treats SGLang/ElevenLabs as optional.

---

# 27. Dashboard

## Environment

Show:
- current machine
- captured profiles
- target profiles
- OS
- CPU
- RAM
- locale
- network

## Reproduction

Example:

```text
TARGET
Windows 11
4 cores
8 GB
en-IN
180 ms
2% loss

CURRENT
macOS
8 cores
16 GB
en-US
12 ms
0% loss
```

Mark every field:

```text
REPRODUCED
APPROXIMATED
UNAVAILABLE
```

## Experiment

```text
Condition             Trials   Failures   Result
-------------------------------------------------
Baseline                 50        1       PASS
180ms                    50        2       PASS
2% loss                  50        3       PASS
180ms + 2% loss          50       37       FAIL
```

## Cause

```text
FAILURE REPRODUCED

Primary condition:
Latency + packet loss

Threshold:
~150–200ms

Interaction:
Confirmed
```

## Regression

```text
SAVE AS REGRESSION
```

Then:

```text
Replay fixed build
PASS
```

---

# 28. Landing page

The planned immersive landing page:

```text
computer
 ↓
inside computer
 ↓
RAM / CPU / storage
 ↓
processor
 ↓
chip-level abstraction
 ↓
different components
 ↓
different computer
 ↓
different OS
 ↓
Morph
```

is visually ambitious but not essential.

### Fallback decision

By approximately **Hour 5–6**, if the live 3D/scroll implementation is consuming meaningful frontend time, switch immediately to:

- pre-rendered sequence
- scroll-triggered transitions
- CSS transforms
- high-quality static visuals
- optional short video

The dashboard is more important than the landing page.

---

# 29. 24-hour build plan

## Phase 1 — 3:00–5:00 PM

Everyone:
- repo/setup
- architecture freeze
- profile schema
- API contract
- task split
- demo application definitions

Adith:
- runtime skeleton

Parth:
- profiler + experiment skeleton

Sarthak:
- frontend shell + API

Rishita:
- dashboard wireframes

**Goal:** all interfaces agreed.

---

## Phase 2 — 5:00–8:00 PM

Adith:
- macOS runtime
- process execution
- telemetry

Parth:
- network shaping
- baseline/treatment
- first failing application

Sarthak:
- environment dashboard
- run controls

Rishita:
- reproduction/failure UI

**Goal:** first real local reproduction.

---

## Phase 3 — 8:00–11:00 PM

Adith:
- Windows adapter
- resource controls

Parth:
- repeated trials
- comparison
- threshold search

Sarthak:
- experiment dashboard
- cause screen
- API integration

Rishita:
- polished experiment/result views

**Goal:** working macOS + Windows demo.

---

## Phase 4 — 11:00 PM–1:00 AM

Everyone:
- full end-to-end test
- crash fixes
- demo fallback recording
- clean setup
- no risky new architecture

**Review 1 target:**

```text
normal
  ↓
target environment
  ↓
failure
  ↓
controlled experiment
  ↓
cause
```

---

# 30. Review 1 — 1:00–5:00 AM

Do not add risky features.

Collect:
- reviewer questions
- missing evidence
- reliability problems
- confusing UI
- technical objections

---

# 31. Phase 5 — 8:00 AM–12:00 PM

Adith:
- Linux/Pi
- runtime hardening

Parth:
- interaction experiments
- statistics
- regression artifacts

Sarthak:
- CI
- production capture
- regression UI

Rishita:
- landing page
- final visual polish

---

# 32. Phase 6 — 12:00–3:00 PM

Only now prioritize:
- cloud worker
- Tin
- n8n
- stronger environment coverage

All sponsor integrations must have local fallbacks.

---

# 33. Phase 7 — 3:00–7:00 PM

Hardening:

- repeated trials
- macOS
- Windows
- Pi
- multiple profiles
- regression replay
- failure recovery
- clean demo environment

**Core feature freeze: 7:00 PM.**

---

# 34. 9:00 PM–12:00 AM

No major architecture changes.

Work on:
- demo
- pitch
- architecture diagram
- screenshots
- sponsor explanation
- limitations
- Q&A
- live-proof script

**Open item: get the actual pitch/demo time box from ACM VIT before this phase.** The live-proof script in Section 39 is designed to run in about two minutes, but the full pitch (problem, demo, architecture, Q&A) needs a confirmed total slot length to know how much of it survives. Confirm this as early as possible, ideally before Review 1, not during this phase.

**Submission/IP note:** if ACM VIT requires a public GitHub repo or a public Devpost-style submission, say so here and confirm before finals — this affects whether any part of the experiment engine can be held back if the team later pursues a formal prior-art/patent assessment. Default assumption until confirmed: submission will be public.

---

# 35. Review 2 and finals

## Review 2 — 1:00–5:00 AM

Prototype should be stable enough for reviewers to interact with.

## Finals — 9:00 AM–3:00 PM

Prioritize:
- live proof
- technical explanation
- presentation
- Q&A
- future scope

---

# 36. Hard cuts

Do not attempt:

- complete hardware emulation
- exact physical CPU clock emulation
- GPU emulation
- custom hypervisor
- full virtual-machine implementation
- perfect cross-OS semantic equivalence
- arbitrary application compatibility
- large distributed cloud platform
- automatic source-code fixing
- research-grade ML root-cause inference
- full observability platform
- support for every language
- support for dozens of OS versions
- authentication/billing
- production-grade enterprise security
- automatic reconstruction of every dependency
- live 3D landing page if it threatens the core product

---

# 37. Stretch features

After the core is reliable:

1. Cloud reproduction
2. Tin execution
3. n8n workflow
4. Linux adapter
5. CPU/concurrency experiment
6. locale experiment
7. filesystem experiment
8. automatic threshold search
9. regression generation
10. production error capture
11. GitHub Action
12. SGLang reporting
13. ElevenLabs demo narration
14. dependency manifest
15. automatic environment diff
16. experiment replay
17. experiment history
18. failure clustering
19. environment recommendations
20. multi-variable experiment scheduling

---

# 38. Review 1 triage

If the team is behind:

### First cut
Immersive landing page.

### Second cut
Cloud/Tin.

### Third cut
n8n.

### Fourth cut
Linux/Pi.

### Fifth cut
Production agent.

### Sixth cut
Advanced statistical analysis.

Never cut:
- environment profiles
- reproduction
- application execution
- telemetry
- controlled experiments
- cause identification
- replay after fix

---

# 39. The one thing judges need to believe

The most important live proof is:

> **Morph actually reproduced the failure instead of merely running the application under a different configuration.**

The minimum proof:

```text
Baseline:
1/50 failed

Latency only:
2/50 failed

Packet loss only:
3/50 failed

Latency + loss:
37/50 failed
```

Then remove the conditions and show the failure rate falls.

Then fix the application and replay:

```text
Fixed build + exact target profile
0/50 failed
```

That establishes:
- reproducibility
- controlled intervention
- interaction detection
- evidence
- regression verification

**Single point of failure:** the entire live demo depends on the network-shaping step (Section 11's `tc netem` / Clumsy calls) reliably producing the same failure rate every rehearsal. If that one mechanism is flaky on demo hardware, there is no fallback that still proves causation live — a recorded backup of exactly this sequence (Section 6's fallback policy) is not optional, it is required, and it must be captured during Phase 4 rehearsal, not improvised the night before.

---

# 40. Final success criteria

Morph is successful if the team can reliably demonstrate:

1. Define or capture an environment.
2. Serialize it.
3. Load it on another machine.
4. Reproduce multiple relevant conditions.
5. Run a real application.
6. Observe a failure.
7. Run controlled experiments.
8. Identify a condition or combination associated with the failure.
9. Show evidence.
10. Fix the application.
11. Replay the same environment.
12. Verify the failure is gone.

The README's core promise is exactly this: reproduce the relevant conditions, experiment until the responsible condition is isolated, then retain the environment as a regression case.

---

# 41. Final product principle

Do not present Morph as:

> "A simulator that can recreate any computer."

Present it as:

> **A portable environment description, a set of OS-specific mechanisms for recreating the controllable parts, and an experiment engine that tests which environmental differences actually change a failure.**

The strongest demo is not the dashboard or the cloud worker.

It is:

**A failure happens only under a particular environment. Morph recreates that environment, proves the failure, changes conditions systematically, finds the condition or interaction that matters, and replays the same environment after the fix to prove the failure is gone.**

That is the core product.
