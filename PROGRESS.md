# Morph Build Progress

> Living status file. Update this after any future work on this codebase so a
> fresh agent or session can pick up with full context. Re-run `/graphify`
> after structural changes to refresh `graphify-out/`.

## Task scope (per user request, kept intentionally narrow)

Only these were in scope for this pass:

1. `morph/profiler/`: environment collectors for CPU, RAM, OS, Locale, Filesystem
2. `morph/engine/`: experiment loop, baseline/treatment runner, threshold search,
   Fisher exact test, causal classification
3. `morph/runtime/adapters/proxy.py`: async TCP proxy for cross-platform latency
   and packet-loss simulation
4. `tests/test_profiler.py`, `tests/test_engine.py`, `tests/test_comparison.py`

Everything else in `docs/architecture.md` (CLI, API server, frontend, telemetry
subprocess runner, regression artifacts, macOS/Windows/Linux native adapters,
network.py/runtime_env.py collectors) is explicitly OUT of scope for this pass.
A minimal `morph/schema/` layer was added anyway since profiler/engine cannot
type their data without it; that is a required dependency, not scope creep.

Git identity for all commits: `parth-garg01` / `parth.garg2024@vitstudent.ac.in`,
no Claude co-author line (per the user's global CLAUDE.md instruction).

## Status: COMPLETE (this pass's scope)

All four features are built, tested, linted clean, and committed. 25/25 tests
pass (`py -3 -m pytest tests/ -q`), the proxy self-check passes
(`py -3 -m morph.runtime.adapters.proxy`), and `ruff check morph/ tests/`
reports no findings. A `code-review` pass was also run and its one real
finding (see below) was fixed with a regression test. `graphify-out/` has been
regenerated to include this pass's `morph/` modules and doc changes (269
nodes, 330 edges, 45 communities as of this write-up). Use `python` (system
default) for graphify's own tooling; use `py -3` specifically for anything
touching this project's code, since that is the interpreter with
psutil/pydantic/pytest/scipy/ruff/distro installed on this machine.

### What exists

- `morph/schema/`: `profile.py` (`EnvironmentProfile` and friends, with
  per-field `FieldStatus`), `telemetry.py` (`RunResult`), `comparison.py`
  (`ComparisonResult`, `ThresholdResult`), `experiment.py` (`TrialBatch`,
  `ExperimentResult`). Minimal dependency layer, not part of the requested
  scope but required by it.
- `morph/profiler/collectors/`: `cpu.py`, `memory.py`, `os_info.py` (uses
  `distro` for Linux distribution version, not kernel version),
  `locale_info.py` (uses Win32 `GetUserDefaultLocaleName` on Windows for a
  proper BCP-47 tag like `en-IN`, since stdlib `locale.getlocale()` only
  returns a Windows display name there), `filesystem.py` (case-sensitivity
  probe via a temp file).
- `morph/profiler/capture.py`: orchestrates the five collectors into one
  `EnvironmentProfile` (`network` field left `None`: no network collector is
  in this pass's scope, that's `runtime/adapters/proxy.py`'s job instead).
- `morph/runtime/adapters/proxy.py`: `ProxyServer` class (asyncio
  `start_server`/`open_connection`, bidirectional relay with injected
  `asyncio.sleep` latency and probabilistic chunk drop for packet loss).
  Supports `async with`. Has an inline `if __name__ == "__main__":`
  self-check (ponytail's "non-trivial logic needs one runnable check" rule)
  since no separate `test_proxy.py` was requested; run it directly with
  `py -3 -m morph.runtime.adapters.proxy`.
- `morph/engine/comparison.py`: `compare_failure_rates()`, Fisher's exact
  test via `scipy.stats.fisher_exact`, returns a `ComparisonResult` with
  `effect_label` in `{no_effect, significant_increase, significant_decrease}`.
- `morph/engine/threshold.py`: `search_threshold()`, binary search over a
  continuous parameter range given a known-safe and known-failing bound.
- `morph/engine/classifier.py`: `classify_failure()`, the three-way rule from
  `architecture.md` section 5.3 (`application_internal` / `environment_caused`
  / `environment_exposed`), plus a fourth `no_effect` outcome for when the
  comparison was not significant or treatment did not actually exceed
  baseline (see the bug fix below).
- `morph/engine/experiment.py`: `run_trials()` (batches N calls to a
  caller-supplied `run_fn: Callable[[], bool]` into a `TrialBatch`),
  `isolate_variables()` (baseline plus N candidate treatments, each compared),
  `detect_interaction()` (2x2 design: neither/A/B/both, confirms an
  interaction only when A alone and B alone show no effect but A+B does),
  and `run_experiment()` (orchestrates isolation, picks the strongest
  significant condition, classifies it). Deliberately takes `run_fn`
  callbacks rather than depending on subprocess/telemetry plumbing:
  `morph/telemetry/` and `morph/runtime/controller.py` are out of scope for
  this pass, and coupling the engine to real subprocess execution would make
  it untestable without a real target app. Wire a real trial runner in when
  the runtime controller exists.
- `tests/test_profiler.py`, `tests/test_comparison.py`, `tests/test_engine.py`:
  25 tests total, all passing.
- `.gitattributes`: normalizes source files to LF (was causing a CRLF
  warning on every commit under Git for Windows).
- `pyproject.toml`: formalizes `pytest` testpaths and `ruff` config (line
  length 110, target py311, rule selection E/F/W/I/UP/RUF). Previously both
  tools ran on implicit defaults.

### Bug fixed during the sanity-check pass

`classify_failure()` accepted a `treatment: TrialBatch` parameter but never
actually read it: classification was decided purely from `baseline.failure_rate`
and the caller-supplied `is_significant` flag. The one production call site
(`run_experiment`) happened to only pass already-filtered `significant_increase`
comparisons, which masked the defect, but the public function itself had no
such guarantee. A future or different caller passing `is_significant=True` for
a *decrease* (for example, verifying a fix) would have been mislabeled
`environment_caused`. Fixed to require `treatment.failure_rate >
baseline.failure_rate` before considering `environment_caused` or
`environment_exposed`; added
`test_classify_no_effect_when_treatment_did_not_actually_increase` as a
regression test. See commit `32c62ea`.

### Also fixed along the way

- `.gitignore` had `/morph` under a leftover "# Go" section from before the
  team settled on Python (per `requirements.txt`). That would have silently
  blocked every commit in this task. Removed.
- `locale_info.py` originally used `locale.getlocale()[0]` everywhere, which
  on Windows returns a display name like `English_India` rather than a BCP-47
  tag. Every example profile in the PRD and architecture doc uses tags like
  `en-IN`. Fixed to call `GetUserDefaultLocaleName` via `ctypes` on Windows.
- `os_info.py` originally used `platform.release()` for the Linux version
  field, which is the kernel version, not the distribution version the PRD's
  example profiles show (`"22.04"`). Fixed to use the already-declared but
  previously unused `distro` dependency.

## Resuming or extending this work

1. Read this file, then `git log --oneline` for the authoritative commit list.
2. The "Not yet done" items below are the next things `architecture.md`
   describes that were explicitly out of scope for this pass. Do not start
   them without the user asking; this file exists to give a future session
   context, not a standing backlog.
3. If asked to extend the engine to run real subprocess trials, that is where
   `morph/telemetry/collector.py` and `morph/runtime/controller.py` from
   `architecture.md` would plug in as the `run_fn` implementation.
4. Keep committing with the `parth-garg01` / `parth.garg2024@vitstudent.ac.in`
   identity, no Claude co-author trailer, and no em dashes anywhere in
   generated content (global CLAUDE.md rule: use commas, parentheses, or
   colons instead).
5. Re-run `/graphify` after any structural change so `graphify-out/` stays
   current.

## Track 2 Status: COMPLETE (Phases 1-6)

Track 2 (Platform, Runtime, Flight Recorder, API, CLI, and E2E Integration) has been fully completed by Adith:

- **Phase 1 (Shared Pydantic Schemas)**: `morph/schema/` (`profile.py`, `telemetry.py`, `experiment.py`, `regression.py`, `comparison.py`).
- **Phase 2 (Telemetry & Runner)**: `morph/telemetry/` (`collector.py`, `parser.py`) and `morph/runtime/runner.py`.
- **Phase 3 (OS Adapters & Controller)**: `morph/runtime/adapters/` (`base.py`, `macos.py`, `linux.py`, `windows.py`) and `morph/runtime/controller.py`.
- **Phase 4 (Flight Recorder & CI Regression Engine)**: `morph/regression/` (`artifact.py`, `replay.py`, `exporter.py`).
- **Phase 5 (FastAPI Backend & Typer CLI)**: `morph/api/` (`app.py`, `routes/profiles.py`, `runs.py`, `experiments.py`, `regressions.py`) and `morph/cli/main.py`.
- **Phase 6 (End-to-End Integration & Verification)**: `tests/test_e2e_integration.py` validating the full loop:
  1. Environment capture and reconciliation
  2. Subprocess execution under simulated conditions with telemetry
  3. Automated causal isolation experiments
  4. Flight recorder `.morph/regressions/` directory bundles
  5. Regression replay against expected invariants
  6. Standalone pytest CI test generation and direct subprocess verification
  7. Full FastAPI REST API workflow
  8. Full Typer CLI workflow

**Total Test Suite**: 92 tests passing with 100% success rate across all components.

---

## Sanity-check pass over Phases 3-6 (Parth)

Integrating Track 2 surfaced 4 Windows-specific bugs (117/117 tests fixed, up
from 113/117), plus a CLI crash on bad input. See commit `b7af641`:

- `morph/telemetry/collector.py`: commands built as raw Windows-path strings
  (the actual convention used by the new CLI/API/e2e code) were being mangled
  by `shlex.split(posix=True)`. Fixed by skipping shlex entirely on Windows —
  `Popen` there accepts a command-line string directly and parses it natively.
- `morph/regression/exporter.py`: `morph export` generated an uncompilable
  file for any regression whose command referenced a Windows path (`\Users`
  read as a broken unicode escape). Fixed with a raw docstring + `repr()`.
- `morph/cli/main.py`: `morph run` on a not-found command crashed with an
  unhandled `TypeError` instead of showing the error (peak_memory_mb is None
  in that case; `:.1f` doesn't accept None).

Also completed a merge (`13558df`) that landed mid-session: `docs/ui-spec.md`
(UI & parameter-control spec) from origin, pulled in via a `git pull` that
started elsewhere while tests were running. Doc-only, no conflicts.

Verified the new flagship demo app, `apps/pool_retry` (Failure B: latency +
packet loss interaction), empirically against real injected proxy conditions:
baseline PASS, latency-alone PASS, loss-alone PASS, combined 8/10 FAIL,
`--fixed` under the same combined conditions 10/10 PASS. Matches the
documented interaction claim exactly.

## Threshold checker + parameter metadata (per docs/ui-spec.md)

Cross-referenced `docs/ui-spec.md` against the codebase per its own
contract (section 6: "the frontend renders entirely from this metadata").
Three things it implies were checked:

- **Profiler**: every MVP parameter's host-detected default (section 2) is
  already covered by `morph/profiler/` — host cores, RAM, locale, timezone.
  Nothing added.
- **Threshold checker**: did NOT exist — nothing validated a requested
  profile against min/max bounds or the cross-field rules in section 5.
  Added `morph/schema/parameters.py` (`MVP_PARAMETERS`: the metadata catalog
  from section 6, scoped to the 7 MVP params that map to existing
  `EnvironmentProfile` fields) and `morph/engine/validator.py`
  (`check_thresholds`, `check_worker_required`, `check_platform_restrictions`,
  `validate_profile`). Two of section 5's rules are NOT implemented —
  `jitter <= latency` and `CPU quota <= cores * 100%` — because neither
  `jitter` nor `cpu_quota` exists as an `EnvironmentProfile` field, and
  adding them is a schema change affecting every phase, not something to do
  unilaterally inside a validator.
- **Tester**: `tests/test_parameters.py` (4 tests) and `tests/test_validator.py`
  (12 tests), all passing.

108/108 core tests pass (`tests/` + these 16 new ones), ruff clean.

## Integration pass: end-to-end network shaping + live dashboard (Adith)

Context: `morph experiment` had never actually shaped a network for the demo
apps. The runtime's proxy adapter started a proxy pointed at `127.0.0.1:80`
that nothing connected to; the apps only honoured their own `MORPH_B_PROXY_*` /
`MORPH_A_*` knobs, which nothing in the runtime set. So every isolation run
came back `no_effect`. Also `/ws/experiment/{id}` was a handshake-only stub and
`morph define -t high-latency` silently produced `network: null`.

### Fixed

- **Interpreter pin** (`morph/telemetry/collector.py`): a command whose first
  token is a bare `python` / `python3` / `python3.x` now runs under
  `sys.executable`. Removes the "wrong interpreter has no deps" failure class
  (system Python 3.14 here is PEP-668 locked, no httpx). Explicit paths pass
  through untouched. POSIX + Windows.
- **`define -t high-latency`** (`morph/cli/main.py`): synthesizes a
  `NetworkInfo` section (capture never populates `network`), set to the
  validated flagship operating point **120 ms / 18 %**.
- **Generic condition hand-off** (`morph/runtime/adapters/base.py`): the
  unprivileged `ProxyAdapter.apply_network` now also exports
  `MORPH_NET_LATENCY_MS` / `MORPH_NET_PACKET_LOSS_PCT`. The three OS adapters
  already copy `ProxyAdapter`'s overrides on their fallback path, so all inherit
  it; native `tc`/`dnctl` paths return earlier and never set them.
- **`apps/netshape.py`** (new): `net_conditions()` + `start_proxy(upstream_port)`.
  `apps/timeout` and `apps/pool_retry` call it to front their own localhost
  server with morph's real `ProxyServer` when a condition is set. `MORPH_B_PROXY_*`
  / `MORPH_A_*` still override.
- **Streaming experiments** (`morph/api/routes/experiments.py`,
  `morph/api/routes/ws.py`): new `POST /experiments/stream` runs the engine in
  a worker thread and forwards every `TrialEvent` to `/ws/experiment/{id}` as
  `{"type":"event",...}`, closing with `{"type":"done","result":...}` /
  `{"type":"error",...}`. `ConnectionManager` gained a per-experiment replay
  log (late subscribers get the whole run) and `emit_threadsafe` /
  `bind_loop` (worker thread -> server loop; self-heals across test clients,
  the `asyncio.Lock` is recreated with the loop). Blocking `POST /experiments`
  and `GET /experiments/{id}` unchanged.
- **React dashboard** (`frontend/src/screens/Experiment.tsx` + `.css`, new;
  `App.tsx`, `Desktop.tsx`, `api/client.ts`, `api/types.ts`): "Run experiment"
  on the desktop dialog opens a live causal-isolation view — one lane per
  condition, per-trial pass/fail ticks, failure-rate bar, `p`-value +
  `SIGNIFICANT ↑` stamp, and a verdict card. Consumes `/experiments/stream` +
  the WebSocket. `openExperimentSocket()` in `api/client.ts`.

### Verified

- `pytest tests/` — **161 pass** (159 + `tests/test_ws_stream.py`), ruff clean.
- `apps/pool_retry`, `apps/timeout`, `apps/locale_parse` self-tests — **19 pass**
  at 120/18. `apps/race` self-tests fail on macOS (CPU-throttle sim, needs the
  Pi) — pre-existing, unrelated to this pass.
- End to end through `POST /experiments/stream` + the WebSocket, flagship
  profile 120/18: baseline 0/12, latency_only 0/12, loss_only 1/12,
  full_treatment **12/12 (p ≈ 7e-7)** -> `environment_caused`.
- `frontend`: `npm run build` + `oxlint` clean.

### Still not done (unchanged from before this pass)

- CPU / memory shaping on macOS is still unenforced env-var stubs; Failure C
  (race) needs the Pi's real cgroup `cpu.max`.
- No cloud / remote-worker backend wired (the "beyond local specs" routing is
  designed in `architecture.md` §12 but not implemented).
- `@app.on_event` was removed in favour of per-request `bind_loop()`; if a
  lifespan handler is added later for other reasons, fold the bind into it.
