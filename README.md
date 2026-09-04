# Morph

> **Test your software in environments you don't physically have.**

Software can work perfectly on a developer's machine and fail for real users because of differences in CPU, RAM, OS, locale, filesystem behaviour, or network conditions. Morph reproduces those conditions on demand — before deployment, or after a failure has already happened — and runs controlled experiments to find out exactly which condition caused it.

**Capture an environment → recreate the conditions that matter → run the application → experiment until you know the cause.**

---

## The problem

"It works on my machine" is usually an environment problem, not a mystery.

| Developer machine | User machine |
|---|---|
| 8-core CPU, 16 GB RAM | 4-core CPU, 8 GB RAM |
| macOS, en-US | Windows, en-IN |
| 12 ms latency, 0% packet loss | 180 ms latency, 2% packet loss |

Some of that is easy to diagnose once someone suspects it — a locale bug, an OS-specific path. The hard failures are the ones caused by **combinations and continuous variation** in conditions, especially network and timing: timeouts, race conditions exposed by timing shifts, retry storms, connection-pool exhaustion, failures that vanish the moment you attach a debugger.

The challenge isn't knowing two machines differ. It's **reproducing the relevant difference and proving whether it actually matters.**

---

## How Morph works

```
CAPTURE  →  REPRODUCE  →  RUN & MEASURE  →  EXPERIMENT  →  ISOLATE THE CAUSE
```

**1. Capture** — A lightweight profiler collects application-relevant conditions from a machine: OS, CPU (arch/cores/clock), RAM, locale, timezone, filesystem behaviour, network latency/packet loss/bandwidth. Stored as a portable environment profile. Runs on demand — not a background service.

**2. Reproduce** — The profile is loaded on another machine (or a cloud worker) and recreated via OS-native controls. macOS, Windows, and Linux each expose different mechanisms for this — one environment format, multiple native adapters underneath.

**3. Run & measure** — The application runs under the reproduced conditions while Morph collects exit status, errors, logs, runtime, resource usage, and network behaviour — not just pass/fail.

**4. Experiment & isolate** — This is the core of the project. Morph doesn't stop at "the user's machine is different." It runs controlled experiments to answer **which** difference caused the failure:

```
Normal network                          → PASS
180 ms latency alone                    → PASS
2% packet loss alone                    → PASS
180 ms latency + 2% packet loss         → FAIL
```

Then narrows the threshold:

```
100 ms → PASS   150 ms → PASS   200 ms → FAIL
```

Output: *"The failure becomes reproducible when latency exceeds ~150–200 ms under the captured packet-loss conditions"* — not "bad network causes the bug."

---

## Controlled, not anecdotal

A single failed run proves nothing. Morph uses a **baseline vs. treatment** comparison over repeated trials:

```
BASELINE   normal network         100 runs →  2 failures
TREATMENT  200ms + 2% loss        100 runs → 71 failures
```

This lets Morph distinguish three cases a developer usually can't tell apart:

- **Application-internal failure** — happens regardless of environment.
- **Environment-triggered failure** — only happens under specific conditions.
- **Environment-exposed application bug** — the condition doesn't cause the bug, it changes timing enough to expose a pre-existing one (e.g. a race condition).

Morph reports which of these it is, rather than blaming the network by default.

---

## Why network conditions specifically

Unlike OS or locale — a small, enumerable set of buckets — network conditions vary continuously (5 ms → 4000 ms latency, 0% → 15% packet loss) and interact with timeouts, retries, connection pooling, and concurrency in ways a developer will often never stumble onto by hand. That makes them the largest source of failures that stay "unreproducible" rather than merely undiagnosed.

---

## Two entry points

**Pre-deployment:** define target environments (low-end Windows laptop, international locale, high-latency mobile network) and test against them before release — catching compatibility and performance issues before users do.

**Post-deployment:** a lightweight agent captures a user's real environment alongside their error logs when something breaks. That capture becomes the exact input to the reproduction loop — turning *"a customer says it sometimes crashes"* into *"we can reproduce the crash under this specific set of conditions."*

Once the cause is found and fixed, the same captured environment becomes a **regression test** — the bug's conditions don't disappear into a closed ticket.

---

## Local vs. cloud execution

Some target environments can't be reproduced locally (an 8 GB machine can't become 16 GB). When required resources aren't available on the developer's machine, the environment profile is sent to a cloud worker with suitable hardware instead.

```
                 Environment Profile
                         │
              ┌──────────┴──────────┐
              ▼                     ▼
        Local Runtime          Cloud Worker
              │                     │
              └──────────┬──────────┘
                         ▼
                    Application → Telemetry
```

---

## Architecture

```
                    Developer UI
                         │
                         ▼
                Environment Profile
                         │
              ┌──────────┴──────────┐
              ▼                     ▼
        Local Runtime          Cloud Runtime
              │                     │
              └──────────┬──────────┘
                         ▼
                    Application
                         │
                         ▼
                      Telemetry
                         │
                         ▼
                  Experiment Engine
                         │
              ┌──────────┴──────────┐
              ▼                     ▼
         Comparison          Parameter Search
              │                     │
              └──────────┬──────────┘
                         ▼
                  Likely Cause / RCA
                         │
                         ▼
                  Developer / CI
```

**Cross-platform design:** one environment profile format, native adapters per OS. We're not pretending a single API can control macOS, Windows, and Linux identically — the profile stays portable, the implementation underneath doesn't have to.

---

## What Morph does *not* claim

Morph reproduces **application-relevant conditions**, not a full hardware emulation:

| Reproduces | Does not claim |
|---|---|
| CPU availability, resource limits | Perfect physical hardware emulation |
| Network latency, packet loss | Turning 8 GB RAM into real 16 GB RAM |
| Locale, timezone | Every GPU characteristic |
| Selected filesystem behaviour | Every kernel/hardware detail |
| Other controllable application-facing conditions | Making macOS literally become Windows |

If a target genuinely requires hardware that doesn't exist locally, cloud execution provides it. This keeps the technical claim honest.

---

## Live demo script

The demo doesn't open with a dashboard — it opens with a failure.

1. Run the app normally → **PASS**
2. Load a captured target environment (Windows, 4 cores, 8 GB RAM, 180 ms latency, 2% packet loss)
3. Run the app again → **FAIL**
4. Show the environment diff
5. Run controlled experiments live: CPU → irrelevant, RAM → irrelevant, locale → irrelevant, latency → contributes, packet loss → contributes, latency + packet loss → **failure**
6. Show the minimal condition set that reproduces it
7. Apply the fix
8. Replay the *exact same* environment → **PASS**

**Detect → reproduce → diagnose → fix → verify** — the whole product in under two minutes.

---

## Limitations

Stated up front, not discovered by a judge mid-Q&A:

- **Physical hardware** — software controls can't reproduce hardware that doesn't exist locally (mitigated by cloud execution).
- **OS-level behaviour** — some behaviour genuinely can't be reproduced from a different OS.
- **GPU behaviour** — exact performance/driver behaviour needs matching hardware.
- **CPU clock speed** — can constrain, not guarantee identical physical behaviour.
- **Nondeterminism** — timing/concurrency/external-service-dependent failures need repeated trials, not single runs.
- **Network realism** — shaping reproduces latency/packet loss/bandwidth, not every property of a real network path.

---

## Prior art & what's actually new

Closest related work: *"Delta Debugging for Cyber-Physical Systems with Flaky Test Executions"* (arXiv 2607.25695) — statistically rigorous causal isolation for flaky failures, via test-input reduction on CPS simulators.

Morph applies that same rigor to a different, larger space: **real machine/environment configuration** (OS, hardware, locale, network) instead of simulator-internal noise, handles **cross-category interaction effects** (hardware × network × OS) rather than a single sequential test trace, and closes the loop with a **production-feedback path** — a real user's captured failure becomes an automatically reproduced, causally isolated test case. No claim of inventing causal isolation; the claim is pointing that machinery at this variable space with this feedback loop.

---

## Sponsor integrations

Structural, not cosmetic:

- **Tin Computer** — hosts remote reproduction jobs when local hardware can't satisfy a target environment.
- **n8n** — orchestrates the pipeline end to end: CI trigger → build test environment → run reproduction → run experiments on failure → notify developer with root cause.
- **SGLang** *(optional)* — self-hosted LLM turns the deterministic experiment engine's output into a plain-English report. It explains evidence; it does not decide the cause.
- **ElevenLabs** *(optional)* — spoken failure/root-cause reveal for the live demo. Not required for the core system.
- **Protoflow** — not used; it's a PCB design tool and doesn't fit a software-only architecture.

---

## Hackathon scope

**MVP:** environment capture, portable profile format, macOS + Windows support (Linux if time allows), CPU/RAM constraints, network latency + packet loss, locale/timezone, application execution + telemetry, environment comparison, controlled parameter variation, clear failure reproduction.

**Stretch:** cloud execution, n8n workflow, Tin Computer integration, automated threshold search, CI integration, production error-log capture, SGLang reporting, saved regression environments.

> A reliable end-to-end reproduction demo beats ten unfinished integrations.

---

## One-line pitch

> Test your software in environments you don't physically have, reproduce failures from machines you don't own, and find the conditions that actually caused them.
