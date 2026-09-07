# Morph

> **Test your software in environments you don't physically have.**

Software works on the developer's machine and fails for real users because of differences in CPU, RAM, OS, locale, filesystem behaviour, or network conditions. Morph reproduces those conditions on demand, before a release or after a failure has already happened, and runs controlled experiments to find out exactly which condition caused it.

**Capture an environment, recreate the conditions that matter, run the application, experiment until you know the cause, and keep the cause as a regression test.**

```
CAPTURE  ->  REPRODUCE  ->  RUN & MEASURE  ->  EXPERIMENT  ->  ISOLATE THE CAUSE  ->  REPLAY
```

---

## The problem

"It works on my machine" is usually an environment problem, not a mystery.

| Developer machine | User machine |
|---|---|
| 8-core CPU, 16 GB RAM | 4-core CPU, 8 GB RAM |
| macOS, en-US | Windows, en-IN |
| 12 ms latency, 0 % packet loss | 180 ms latency, 2 % packet loss |

Some of that is easy to diagnose once someone suspects it: a locale bug, an OS-specific path. The hard failures are caused by **combinations and continuous variation** in conditions, especially network and timing: timeouts, race conditions exposed by timing shifts, retry storms, connection-pool exhaustion, failures that vanish the moment a debugger attaches.

The challenge isn't knowing two machines differ. It's **reproducing the relevant difference and proving whether it actually matters.**

---

## What Morph does

**1. Capture.** A one-shot profiler reads the application-relevant conditions of a machine (OS, CPU, RAM, locale, timezone, filesystem behaviour, network latency, packet loss, bandwidth) into a portable JSON profile. A failing user's machine ships the same profile with its error logs.

**2. Reproduce.** The profile is applied on another machine through OS-native controls (`tc`/netem and cgroups on Linux, `dnctl`/pf on macOS, a Windows adapter) or, with no root at all, through a user-space TCP proxy that models a real network path: a per-direction delay line, and packet loss as a retransmission stall rather than corrupted bytes.

**3. Run and measure.** The application runs under the reproduced conditions while Morph records exit status, errors, stdout/stderr, timing, peak memory and provenance (seed, host fingerprint, profile hash) for every trial.

**4. Experiment and isolate.** Morph runs controlled experiments to answer *which* difference caused the failure:

```
baseline                     0 / 12   E = 1.0                     (morph demo, real run)
120 ms latency alone         0 / 12   E = 1.0
18 % packet loss alone       0 / 12   E = 1.0
latency + packet loss        9 / 9    E = 102   DECISIVE, stopped after 9 pairs
```

then narrows the boundary with a credible interval:

> *The lock lease breaks when latency exceeds about 134 ms (90 % credible interval 111 to 161 ms) under the captured packet-loss conditions.*

**5. Replay.** The captured environment becomes a regression bundle and a generated pytest file, so the bug's conditions do not disappear into a closed ticket.

---

## Statistics that stay honest while you watch

Morph's console shows evidence accumulating live. That is only legitimate because the engine uses statistics that remain valid at every stopping time.

- **Anytime-valid e-values** (`morph/engine/anytime.py`). Trials run in matched baseline/treatment pairs. Under "no difference" a discordant pair is a fair coin; against that null Morph runs Robbins' Beta-mixture likelihood ratio, an e-process. By Ville's inequality the false-positive rate stays at α no matter when you stop looking, so a lane can stop the moment it is decisive. In simulation the false-positive rate under continuous monitoring is about 2 % at α = 5 %, and the flagship latency-plus-loss fault is decided in about 7 pairs.
- **Sequential isolation** (`morph/engine/sequential.py`). Round-robin over baseline and every candidate condition, with a K/α evidence budget so the family-wise error stays at α across K conditions. Interleaving also cancels host drift.
- **Probabilistic bisection for boundaries** (`morph/engine/boundary.py`). A posterior over the failure boundary, probed at its median and updated through a logistic dose-response model whose floor and ceiling (how flaky the app is) are learned from the same trials. Two extra hypotheses, "never fails in range" and "always fails", stop it from inventing a boundary. Over 40 noisy simulated runs on the same trial budget the median error was 4 ms against 21 ms for plain bisection, and the worst case 24 ms against 150 ms.
- **Batch mode** keeps the classic design: one-sided Fisher exact tests with Holm-Bonferroni across candidates, risk differences with Newcombe intervals, and an explicit warning when the trial count is too small to ever reach significance.
- **Interaction and minimality.** A 2x2 design with a Bayesian test for super-additivity (is latency + loss worse than the sum of its parts?) and delta debugging over conditions (`morph/engine/minimize.py`) that returns the 1-minimal failing set.
- **Four verdicts.** `environment_caused`, `environment_exposed` (the condition only changes timing enough to reveal a pre-existing bug such as a race), `application_internal`, `no_effect`.

The maths, with citations, is in [`docs/how-it-works.md`](docs/how-it-works.md).

---

## Honesty is enforced in code

Morph reproduces **application-relevant conditions**, not a full hardware emulation, and it says so per field.

| Reproduces | Does not claim |
|---|---|
| CPU quota and core limits (Linux cgroups) | Perfect physical hardware emulation |
| Network latency, packet loss, bandwidth | Turning 8 GB of RAM into 16 GB |
| Locale, timezone, resource limits | GPU characteristics |
| Selected filesystem behaviour | Making macOS literally become Windows |

- Every profile field is stamped by the adapter that applied it: `REPRODUCED`, `APPROXIMATED` (for example, the user-space proxy shapes only traffic routed through it) or `UNAVAILABLE`, with a reason.
- A trial the application could not even attempt (exit code 2, a missing binary, a bad working directory) is recorded as **invalid**, retried, and reported as a setup problem. It never enters a failure rate.
- No boundary is reported when the evidence says there isn't one in range.
- Cloud dispatch to a worker with the hardware the profile needs is explicit (`morph run --cloud`) and fails loudly. There is no silent fallback to a host that was just judged unable to reproduce the profile.

---

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt && pip install -e .

cp .env.example .env                          # optional: tokens, worker host, deploy origins (gitignored)
morph doctor                                  # what this host can shape, stale rules, worker status
morph demo                                    # the flagship experiment, end to end, no root needed

morph capture -o here.json                    # profile this machine
morph define -t high-latency -o target.json   # or start from a template
morph run -p target.json -c "python -m app"   # one run under the conditions
morph experiment -p target.json -c "python -m app"            # sequential isolation (default)
morph experiment -p target.json -c "python -m app" --mode batch -n 10
morph threshold -p target.json -c "python -m app" --parameter network.latency_ms --low 0 --high 400
morph minimize  -p target.json -c "python -m app"             # minimal failing condition set

morph save --id checkout-lease -p target.json -c "python -m app"  # regression bundle
morph replay checkout-lease
morph export checkout-lease                                    # standalone pytest invariant
```

Three surfaces share one service layer:

- **CLI**: everything above, with `--json` on every command for scripting.
- **TUI**: `morph tui` is a full-screen console with live lanes, evidence tracks, the Bayesian boundary gauge and a verdict card. `morph tui --demo` replays a real run with no root, network or target app. See [`docs/tui.md`](docs/tui.md).
- **GUI**: `morph serve` starts a local API and, after `npm run build`, serves the React dashboard from the same port (projects, run, experiment, threshold, regressions, environment diff). Hosting notes in [`docs/deployment.md`](docs/deployment.md).

---

## The failure corpus

`apps/` holds deliberately broken applications, one per class of environmental failure. Each ships a `--fixed` variant so that replaying the captured environment after the fix is the regression test. Details and measured failure rates in [`docs/faultyapps.md`](docs/faultyapps.md).

| App | Failure class | Condition Morph injects |
|---|---|---|
| `timeout` | Deadline tripped by round-trip time | `network.latency_ms` |
| `pool_retry` | Lock lease expires mid-payment (latency x loss interaction) | latency + packet loss |
| `race` | Lost update exposed by CPU starvation | `cpu.quota_percent` / yield knob |
| `locale_parse` | Decimal separator parsed with the wrong locale | `locale.locale` |
| `fd_limit` | Handle exhaustion under a low file-descriptor limit | `process.fd_limit` |
| `tz_dst` | Scheduler skips an hour across a DST transition | `locale.timezone` |

---

## Architecture

```
            CLI (Typer)        TUI (Textual)       GUI (React + Vite)
                 |                  |                     |
                 +---------- service layer: FastAPI, /api/v1, WebSocket streams ----------+
                                          |
                          experiment engine (morph/engine)
        anytime e-values . sequential isolation . probabilistic bisection . Holm . interaction . ddmin
                                          |
                          runtime + telemetry (morph/runtime, morph/telemetry)
        controller -> adapters: Linux tc/cgroups . macOS dnctl/pf . Windows . user-space proxy
        collector: process groups, rlimits, invalid-trial flag, provenance, fidelity report
                                          |
                          target application                explicit --cloud dispatch
                                                            to an SSH worker (Pi, GCP)
```

One environment-profile format, native adapters per OS: the profile stays portable, the implementation underneath doesn't have to. Module-by-module detail in [`docs/architecture.md`](docs/architecture.md); cloud workers in [`docs/cloud.md`](docs/cloud.md); connecting a project in [`docs/projects.md`](docs/projects.md).

---

## Live demo script

The demo doesn't open with a dashboard. It opens with a failure.

1. Run the checkout service normally: **PASS**.
2. Load a customer's captured profile (Windows, 4 cores, 8 GB, 180 ms, 2 % loss). Run again: **FAIL**.
3. Show the environment diff.
4. Run sequential isolation live: cpu irrelevant, RAM irrelevant, locale irrelevant, latency contributes, loss contributes, latency + loss **decisive**, stopped early.
5. Show the 2x2 interaction and the minimal failing set: `{latency, packet loss}`.
6. Locate the boundary with its credible interval.
7. Apply the fix. Replay the *same* environment: **PASS**, regression locked.

**Detect, reproduce, diagnose, fix, verify**: the whole product in under two minutes.

---

## Limitations

Stated up front:

- **Physical hardware.** Software controls can't reproduce hardware that doesn't exist locally (mitigated by explicit cloud execution).
- **OS-level behaviour.** Some behaviour genuinely can't be reproduced from a different OS.
- **CPU and memory on macOS and Windows.** Only Linux cgroups enforce quotas; elsewhere those fields are reported `UNAVAILABLE`, and the demo apps expose root-free stand-in knobs.
- **Network realism.** Shaping reproduces latency, loss and bandwidth, not every property of a real path.
- **Nondeterminism.** Timing and concurrency failures need repeated trials; that is what the sequential engine is for.

---

## Prior art and what's new

Morph invents no new statistics. It composes established ones and points them at a space nobody had: the real machine.

- E-processes and safe anytime-valid inference: Ramdas, Grünwald, Vovk and Shafer (2023); Turner, Ly and Grünwald (2024) for 2x2 tables.
- Probabilistic bisection: Horstein (1963); Waeber, Frazier and Henderson (2013); Watson and Pelli's QUEST (1983) for the response model.
- Delta debugging: Zeller and Hildebrandt (2002). Multiple comparisons: Holm (1979).
- Closest related tool: delta debugging for flaky cyber-physical test executions (arXiv 2607.25695), which isolates causes on simulator inputs.

What is new is the variable space (OS x hardware x locale x network, with cross-category interactions), a live console whose numbers are valid at every glance, and the closed loop from a customer's captured failure to a reproduced, isolated, minimal, replayable regression with a generated CI test.

---

## Development

```bash
pytest -q                      # unit + integration suite
pytest -q apps -m "not slow"   # demo-app contract tier
ruff check morph tests apps
cd frontend && npm ci && npm run lint && npm run build
```

CI runs lint, the suite on Linux and macOS across Python 3.11 and 3.12, the frontend build, and the demo-app corpus. `MORPH_NO_NETWORK=1` keeps every test off the network.

---

## One-line pitch

> Test your software in environments you don't physically have, reproduce failures from machines you don't own, and find the conditions that actually caused them.
