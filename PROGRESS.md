# Morph Build Progress

> Living status file for the current implementation pass. Update this after every
> commit so a fresh agent/session can pick up exactly where the last one left off.
> Also re-run `/graphify` after this task is complete (or after major structural
> changes) to refresh `graphify-out/`.

## Task scope (per user request, do not expand)

Only these are in scope for this pass:

1. `morph/profiler/` — environment collectors for CPU, RAM, OS, Locale, Filesystem
2. `morph/engine/` — experiment loop, baseline/treatment runner, threshold search,
   Fisher exact test, causal classification
3. `morph/runtime/adapters/proxy.py` — async TCP proxy for cross-platform latency
   and packet-loss simulation
4. `tests/test_profiler.py`, `tests/test_engine.py`, `tests/test_comparison.py`

Everything else in `docs/architecture.md` (CLI, API server, frontend, telemetry
subprocess runner, regression artifacts, macOS/Windows/Linux native adapters,
network.py/runtime_env.py collectors) is explicitly OUT of scope for this pass.
The minimal `morph/schema/` layer was added anyway because profiler/engine
cannot type their data without it — this is a required dependency, not scope
creep.

After all four features are in: ~30 small commits total, then a sanity-check
pass (run the full test suite, fix anything broken, confirm imports work).

Git identity for all commits: `parth-garg01` / `parth.garg2024@vitstudent.ac.in`,
no Claude co-author line (per user's global CLAUDE.md instruction).

## Status: IN PROGRESS

### Done (committed)

- [x] Removed `/morph` from `.gitignore` (was a leftover Go-language gitignore
      rule that would have silently blocked every commit in this task — project
      settled on Python per `requirements.txt`).
- [x] Scaffolded package dirs: `morph/{schema,profiler/collectors,engine,runtime/adapters}`,
      `tests/`, all with `__init__.py`.
- [x] `morph/schema/profile.py` — `FieldStatus`, `ProfileField`, `OSInfo`, `CPUInfo`,
      `MemoryInfo`, `LocaleInfo`, `FilesystemInfo`, `NetworkInfo`, `EnvironmentProfile`.
- [x] `morph/schema/telemetry.py` — `RunResult` (minimal: exit_code, stdout,
      stderr, duration_ms, passed, error_type, error_message — dropped run_id/
      timestamp from the architecture doc's version since nothing in this pass's
      scope needs them).
- [x] `morph/schema/comparison.py` — `ComparisonResult` (with
      `baseline_failure_rate`/`treatment_failure_rate` as computed properties,
      not stored fields), `ThresholdResult`.
- [x] `morph/schema/experiment.py` — `TrialBatch` (failure_rate computed
      property), `ExperimentResult`.
- [x] `morph/profiler/collectors/cpu.py` — `collect_cpu()` via psutil +
      platform.machine(). Note: does NOT use py-cpuinfo despite it being in
      requirements.txt/architecture doc — psutil+platform covers arch/cores/
      clock without the extra dependency; py-cpuinfo is slow to import (probes
      via subprocess on some platforms) and unnecessary for this field set.
      Revisit only if a specific field genuinely needs it.
- [x] `morph/profiler/collectors/memory.py` — `collect_memory()` via psutil.
- [x] `morph/profiler/collectors/os_info.py` — `collect_os()`, maps
      platform.system() to darwin/windows/linux family strings.
- [x] `morph/profiler/collectors/locale_info.py` — `collect_locale()` via
      stdlib `locale` + `time.tzname` (no `tzdata`/timezone-database dependency
      needed for this — that's for *applying* timezones later, not capturing
      the current one).
- [x] `morph/profiler/collectors/filesystem.py` — `collect_filesystem()`,
      detects case sensitivity by probing a temp file's uppercased path.

### Not yet done

- [ ] `morph/profiler/capture.py` — orchestrator that calls all 5 collectors
      and returns an `EnvironmentProfile` (network=None since no network
      collector is in scope this pass).
- [ ] `tests/test_profiler.py` — exercises capture_environment() end to end,
      checks every field has status=CAPTURED and sane types/ranges.
- [ ] `morph/runtime/adapters/proxy.py` — async TCP proxy (asyncio), listens
      on a local port, forwards to an upstream host:port, injects
      `asyncio.sleep(latency_ms/1000)` per read and probabilistically drops
      chunks by `packet_loss_percent`. Needs a `ProxyServer` class with
      start()/stop(), plus a `if __name__ == "__main__"` self-check per
      ponytail's "non-trivial logic needs one runnable check" rule (no
      separate test_proxy.py was requested, so the self-check lives inline
      instead of as a pytest file).
- [ ] `morph/engine/comparison.py` — `compare_failure_rates()` using
      `scipy.stats.fisher_exact`, returns `ComparisonResult`.
- [ ] `tests/test_comparison.py` — no-effect case, significant-increase case,
      edge cases (zero totals).
- [ ] `morph/engine/threshold.py` — binary search `search_threshold()` over a
      parameter range using repeated trials at each midpoint.
- [ ] `morph/engine/classifier.py` — `classify_failure()` implementing the
      3-way rule from architecture.md section 5.3 (application_internal /
      environment_caused / environment_exposed) based on baseline vs treatment
      failure rates.
- [ ] `morph/engine/experiment.py` — main experiment loop: `run_trials()`
      (batches N calls to a caller-supplied `run_fn: Callable[[], bool]` into
      a `TrialBatch`), single-variable isolation loop, 2-variable interaction
      detection (neither/A/B/both), orchestrator tying it to classifier +
      comparison. Deliberately takes a `run_fn` callback rather than depending
      on subprocess/telemetry plumbing — `morph/telemetry/` is out of scope
      for this pass, and coupling the engine to real subprocess execution
      would make it untestable without a real target app. Revisit when
      `morph/runtime/controller.py` exists to wire a real trial runner in.
- [ ] `tests/test_engine.py` — run_trials counts, isolation loop picks the
      right candidate, interaction detection flags the interacting pair,
      threshold search converges, classifier picks the right label in all 3
      cases.
- [ ] Full commit sequence (~30 total, ~9 done so far — see `git log --oneline`
      for the authoritative list, this file is a summary not a duplicate).
- [ ] Final sanity check pass: `pip install -r requirements.txt` (or confirm
      deps already available), `pytest tests/ -v`, fix anything broken, then
      re-run `/graphify` to refresh `graphify-out/` with the new modules.

## Resuming this task

1. Read this file, then `git log --oneline -20` to see exactly which commits
   landed.
2. Check which files under "Not yet done" above already exist on disk (a
   session may have written a file but not yet committed it) before writing
   anything — don't overwrite in-progress work blindly.
3. Continue down the "Not yet done" list in order — later items depend on
   earlier ones (engine/experiment.py needs comparison.py and classifier.py
   first).
4. Keep committing after each file/logical unit, using the
   `parth-garg01`/`parth.garg2024@vitstudent.ac.in` identity, no Claude
   co-author trailer.
5. Update this file's checkboxes as you go — don't let it drift out of sync
   with `git log`.
6. When everything above is checked off and tests pass, run `/graphify` to
   regenerate `graphify-out/`, then delete or archive this file's "Not yet
   done" section (or mark the task fully complete) since it will no longer be
   needed by a future session.
