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
finding (see below) was fixed with a regression test.

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

### Not yet done (out of scope for this pass, listed for context only)

- CLI (`morph/cli/`), API server (`morph/api/`), frontend (`frontend/`)
- `morph/telemetry/` (real subprocess-based trial runner)
- `morph/runtime/controller.py` and the macOS/Windows/Linux native adapters
  (`adapters/macos.py`, `windows.py`, `linux.py`); `proxy.py` is the only
  adapter built so far
- `morph/regression/` (`.morph/regressions/` artifacts, replay, CI exporter)
- `network.py` and `runtime_env.py` profiler collectors
- Demo failure corpus (`demo_apps/`)
