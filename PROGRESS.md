# Morph Build Progress

> Living status file. Update this after any future work on this codebase so a
> fresh agent or session can pick up with full context.

## Where things stand (2026-09-07, branch `feat/production-hardening`)

A full audit-and-fix pass was run over every layer (engine, runtime, API, CLI,
TUI, GUI, demo apps, docs) ahead of the hackathon's first review
(1:00 to 5:00 am on 2026-09-08). Work lives on `feat/production-hardening`,
built in a git worktree so the landing-page session on `feat/landing-page`
was never disturbed. Commit identity: `Ad1th <adith2505@outlook.com>`, no AI
attribution trailers, no em dashes in docs or UI copy.

**Verified state:** `pytest tests` 465 passed / 1 skipped; `pytest apps -m
"not slow"` 40 passed (slow statistical tier 17 passed, 1 Linux-only skip);
`ruff check morph tests apps` clean; `npm run build` and `oxlint` clean;
`morph demo` runs end to end in 1 min 46 s on macOS with no root and reaches
`environment_caused` (E = 102 after 9 pairs, anytime p = 0.0098).

### Research-grade engine additions (`morph/engine/`)

- `anytime.py`: exact paired e-values (Robbins' Beta-mixture against the
  fair-coin conditional null). Monte Carlo: 2.1 % false positives under
  continuous monitoring at alpha 5 %, power 1.0 at 30 pairs for 5 % vs 70 %.
- `sequential.py`: paired round-robin isolation with a K/alpha evidence
  budget (family-wise error at alpha) and early stopping. Default mode for
  `morph experiment`, the API, the TUI and the GUI.
- `boundary.py`: probabilistic bisection (Horstein; Waeber, Frazier and
  Henderson) with a logistic dose-response model, learned floor/ceiling, two
  no-boundary hypotheses, credible intervals, `increasing=False` for
  parameters that hurt when smaller (fd limits). 40 noisy runs: median error
  4 ms vs 21 ms for plain bisection, worst 24 ms vs 150 ms.
- `comparison.py`: one-sided Fisher, Holm-Bonferroni across candidates,
  risk difference with Newcombe intervals, `minimum_trials_for_significance`.
- `experiment.py`: Bayesian 2x2 interaction test (`interaction_probability`,
  Jeffreys posteriors, confirmed only above 0.95 with weaker singles).
- `minimize.py`: ddmin over conditions, `batch_oracle`.
- `errors.py`: `InvalidTrialError`; invalid trials (exit 2, 126, 127, launch
  failures) are retried three times then reported as a setup problem, never a
  failure. `blame.py` no longer fabricates file/line/fix.

### Runtime (`morph/runtime`, `morph/telemetry`, `morph/cloud`)

- Proxy rewritten: per-direction delay line (latency_ms is RTT), loss as a
  retransmission stall (max(200 ms, 3 x RTT), doubling), never corruption;
  bandwidth token bucket, jitter, `seed`/`MORPH_SEED`. `tests/test_proxy.py`.
- Adapters: per-field fidelity report (`fidelity_report()`), crash-safe
  shaping state in `~/.morph/state/shaping.json` (`morph/runtime/state.py`),
  `tc qdisc replace`, real pf anchor on macOS root path, honest capabilities.
- Controller never dispatches to a worker; `--cloud` goes through
  `morph/cloud/dispatch.py` and fails loudly. One `cloud:` config block
  (`WorkerConfig` is an alias). `MORPH_NO_NETWORK=1` keeps tests offline.
- Collector: process-group kill, bounded 2 MB capture, `errors="replace"`,
  rlimits clamped, provenance (`seed`, `morph_version`, `host_fingerprint`,
  `profile_hash`, `adapter`, `fidelity`) on every `RunResult`.
- Security: regression ids validated and store-confined; GitHub token only via
  `GIT_CONFIG_*` env, never argv or `.git/config`; SSH `BatchMode`,
  `StrictHostKeyChecking=accept-new`.
- Profiler: IANA timezone, POSIX locale plus BCP-47 `language_tag`.

### API and CLI (`morph/api`, `morph/cli`)

- `service.py` is the single orchestration path for CLI, API and TUI.
- CORS restricted to localhost origins, `allow_credentials=False`,
  TrustedHost, loopback bind by default; `/projects/github/cli-token` removed;
  ids validated; upload symlink/size guards; setup errors are HTTP 422 / CLI
  exit 2; lifespan cancels jobs and cleans shaping on shutdown.
- New: `/api/v1` prefix (old paths kept), `/health`, `/version`,
  `POST /threshold/stream` + `/ws/threshold/{id}`, `DELETE /threshold/{id}`,
  `POST /minimize`, `POST /profiles/fidelity`, `GET/DELETE /experiments`.
- CLI: `--mode sequential|batch`, `--max-rounds`, `--alpha`, `threshold
  --method bayes|bisect`, `minimize`, `doctor`, `demo`, `--version`, pure
  `--json` on every path, documented exit codes (0/1/2/3/124).
- CI: frontend job, ubuntu + macOS matrix, blocking apps fast tier.

### TUI (`morph/tui`)

Redesigned on a wine-palette Textual theme (`theme.py`): sequential evidence
tracks, DECISIVE stamps, Bayesian gauge with credible band, help overlay,
command palette, cancel, evidence pane, responsive at 80x24 and up. See
`docs/tui.md`.

### GUI (`frontend/`)

Rebuilt on one design system (`src/theme/tokens.css`): rail + router,
persistent run draft, Projects / Run / Experiment / Threshold / Regressions /
Environment screens, live evidence tracks, dose-response chart, honest
fidelity chips, no OS skins (the OS switcher is now the run-target badge).
The landing page (`/`) belongs to the `feat/landing-page` branch; `main.tsx`
is structured so it can claim `/` without touching the app.

### Demo apps (`apps/`) and docs

Six apps (`timeout`, `pool_retry`, `race`, `locale_parse`, `fd_limit`,
`tz_dst`), shared `apps/conftest.py`, markers `slow`/`needs_linux`/
`needs_root`, `profiles/` for each. Docs rewritten: `docs/how-it-works.md`
(new, the maths with citations), `architecture.md`, `faultyapps.md`,
`cloud.md`, `projects.md`, `ui-spec.md`, `tui.md`, README. Pitch deck at
`docs/deck/morph-deck.html`.

## Known gaps

- CPU/memory shaping only enforces on Linux cgroups (reported UNAVAILABLE
  elsewhere); `apps/race` uses a yield knob off-Linux.
- `tc netem` on the Raspberry Pi and real-cgroup race rates are unmeasured.
- The 2D surface heatmap has no GUI screen (API and TUI only).
- `PROFILES_DIR` and the regressions dir are CWD-relative.
- Audit reports from this pass were kept outside the repo; the findings are
  reflected in tests.

## Resuming

1. `git log --oneline` on `feat/production-hardening` is authoritative.
2. `morph doctor`, then `morph demo`, then `pytest -q` before trusting a change.
3. Keep the honesty rules: no fabricated numbers, invalid trials are not
   failures, every field carries its fidelity.
