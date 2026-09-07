# `morph tui` — the live console

A full-screen terminal app (Textual) for running experiments and watching them
resolve. Runs anywhere a terminal does; also servable in a browser with
`textual serve "morph tui"`.

```
morph tui           # live
morph tui --demo    # replay recorded engine runs (no root / network / target app)
python -m morph.tui
```

It fits 80×24 (single column, lanes stacked, footer always visible) and opens
up to two panes at 120 columns and wider. Every screen has a one-row title, a
status bar (mode, project, worker target, phase, trials done/total, elapsed,
the leading e-value and a progress bar while a run is in flight) and a footer.

## Keys that work everywhere

| key | action |
|---|---|
| `F1` / `?` | help overlay: every binding on the current screen |
| `Ctrl+P` | command palette: run / search / replay / cancel, open any screen or connected project, load profile, toggle theme |
| `F2` | theme: `morph-dark` ↔ `morph-light` |
| `Ctrl+G` | jump home from any depth |
| `esc` | back — or, while a run is in flight, **stop it** (so is `c`) |
| `Ctrl+Q` | quit |

Run/save/toggle actions are `Ctrl` chords (`^r`, `^s`, `^t`, …) so they work
while a text box has focus. Plain letters (`e m t n p r`, `c`, `space`) act only
when no Input has focus.

## Home

Six cards, keyboard-first: `e` Experiment · `m` Monitor · `t` Threshold ·
`n` Environment · `p` Projects · `r` Regressions.

## Projects — add a repo, then run it

Type a GitHub repo (`owner/repo` or a URL) or a local path, optionally tick
*install deps*, and **Connect** (or press enter). Auth is checked in the
background (`gh auth token` never blocks the screen). The connected project is
remembered under `~/.morph/projects/`.

With a project selected, `^r` / `e` opens Experiment, `m` Monitor, `t`
Threshold, with its command pre-filled and every trial running from its
directory. `del` removes it. See [`projects.md`](projects.md).

## Experiment — causal isolation

Enter a target profile (blank → this host + latency/loss; a mistyped path is an
error, never a silent substitute), a command and a per-condition trial budget,
then `^r`. Each condition gets a **lane**; the right pane holds an **Evidence**
panel (the latest failing trial's condition, error type and stderr/stdout tail)
and the log.

**Sequential mode (default, `^t` toggles).** Baseline and candidates run
round-robin as matched pairs and each candidate's anytime-valid **e-value**
streams live: an `E` readout, a sparkline of its history, and a bar growing
toward the `│` threshold line (`E ≥ K/α`, K = number of candidates). Because
e-values are anytime-valid it is legitimate to watch them and stop when they
cross: a lane stamps **DECISIVE**, stops consuming trials, and reads
`stopped early after N pairs`. The title bar tints for a beat (no layout
shift).

**Batch mode.** Fixed-size batches; the Fisher's-exact p-value appears only
once a batch is complete (no peeking), with a `SIGNIFICANT ↑` stamp.

The **verdict card** reveals line by line (~0.6 s): the diagnosis
(`ENVIRONMENT-CAUSED` / `ENVIRONMENT-EXPOSED` / `APPLICATION BUG` /
`NO EFFECT`), strongest condition, `E` + pairs + anytime p (or Fisher p in
batch mode), the classification, any engine warnings (e.g. *n too small to
ever reach significance*), and the minimal failing condition set when the
engine provides one. For a latency+loss target the **2×2 interaction matrix**
resolves from the same four batches — three cells green, "both" rose — with
`P(interaction)` when the engine reports it.

`^s` freezes the run as a regression bundle under `.morph/regressions/`,
recording the project's working directory so a replay runs from the same place.

## Monitor: live tuning

A task-manager view, not a statistical test. The conditions pane lists every
knob the dashboard has, in the same groups:

- **network**: on/off, connection type (ethernet, wifi, cellular, vpn,
  satellite), latency, packet loss, bandwidth, jitter
- **cpu and memory**: cores, cpu quota, ram, ram pressure, swap, architecture,
  os family
- **locale and time**: locale, timezone
- **filesystem**: case sensitivity, read-only, disk space, disk read and write
  latency
- **process**: timeout, max processes, threads, open files

Numeric knobs are sliders (`←/→` nudge, `Shift+←/→` jump, `Home/End` to the
ends); choices and toggles cycle with the same keys. `Tab` moves between them
and the pane scrolls. Every knob shows its fidelity badge for this host:
`REPRODUCED`, `APPROXIMATED` or `UNAVAILABLE` (a Mac cannot cgroup-limit CPU
or RAM, so cores, quota and ram are carried as runtime hints such as
`OMP_NUM_THREADS`, `GOMAXPROCS` and `NODE_OPTIONS` and read `APPROXIMATED`,
never `REPRODUCED`), or `CAPTURED`
when the value is simply recorded into the profile.

Changing a knob re-runs the command under the new conditions (debounced, one
at a time; `Space` toggles auto-run, `Ctrl+R` runs once). The right pane is a
rolling graph of the last ~60 runs: duration, CPU and peak memory sparklines
with a current-value readout, plus a pass/fail strip.

When a slider crosses a boundary the runs have revealed, it gets a red `⚠`
and the panel names the condition, its value and the reason, taken from the
last failing run. A boundary is only attributed to a knob when the runs
actually split on it.

If the connected project has no runnable command, or its command cannot
launch here, the Monitor keeps working on a per-project performance model
seeded from the repository and commit: the same repo always draws the same
graphs and crosses the same boundaries, a different repo gets different
ones. The graph title and status bar say `SIMULATED` and why. `--demo` uses
the pool_retry-shaped model with no target app.

## Threshold — failure boundary

Pick a parameter (`network.latency_ms` / `network.packet_loss_percent`), a
range, a command, and a trial budget, then `^r`.

**Bayesian (default, `^t` toggles).** Probabilistic bisection with a flaky
oracle: the gauge's gold `[ … ]` bracket is the 90 % **credible interval**,
which shrinks with every probe; `▲` is the posterior median; the strip under
the track is the posterior density. `trials` is the total budget. When the
engine concludes there is *no* boundary in range it says so — `never fails
here` / `already failing at low` with its probability — instead of inventing a
boundary at zero.

**Bisection.** The classic halving search (`trials` runs per probe) on the same
gauge: green known-safe / rose known-failing halves and the band between
`[safe` and `fail]`.

## Environment — capture / shape / reconcile

Captures this host in the background, then lets you pick a template (host /
high-latency / constrained / raspberry-pi-ish), edit numeric rows inline
(select a row, type, enter), and load/save profile JSON (errors — a bad file,
an unwritable path — land in the status bar). **Reconcile** (`^r`) stamps every
field `REPRODUCED` / `APPROXIMATED` / `UNAVAILABLE` for the current host;
`^n` re-captures.

## Regressions — flight recorder

Lists `.morph/regressions/` bundles. **Replay** (`^r`) re-runs the selected
bundle under its recorded environment and from its recorded directory, live,
then shows `REGRESSION LOCKED` / `REGRESSION OPEN` against its tolerance, with
the failing trial's evidence. **Export test** (`^o`) writes the standalone
pytest invariant.

## Cancelling

`esc` or `c` (or the Stop button) while a run is in flight cancels it
cooperatively: the engine's `on_event` callback raises between trials, so the
current trial finishes, the runtime's `finally` restores the host (shaping is
torn down), and the screen reports `cancelled`. Leaving a screen mid-run does
the same.

## Demo mode

`--demo` replays event streams the real engines produced over deterministic
synthetic trial functions modelling `apps/pool_retry` at 120 ms + 18 % loss:
`run_sequential_experiment` for the Experiment screen (evidence crossing the
threshold, an early stop at 9 pairs, ENVIRONMENT-CAUSED), `locate_boundary`
for Threshold (the credible band shrinking onto ~94 ms), and `run_trials` for
a regression replay. Nothing executes; the status bar says DEMO throughout.

## Theme

`morph/tui/theme.py` defines `morph-dark` (default) and `morph-light` as
Textual `Theme`s with semantic variables — `$pass` green, `$fail` rose,
`$evidence` gold, `$bone` / `$bone-dim` text — used by the stylesheet and, via
`palette(widget)`, by every Rich-rendered widget, so `F2` restyles lanes, gauge
and matrix too.

## How it's wired

The engine takes an optional `on_event(TrialEvent)` callback
(`morph/schema/events.py`) threaded through `run_sequential_experiment`,
`run_experiment`, `locate_boundary`, `search_threshold` and `run_trials`.
`morph/tui/orchestrator.py` builds `RunResult`-returning trial runners and
drives the engine; `RunnerScreen` (`morph/tui/screens/base.py`) runs that in a
Textual thread worker, wraps `on_event` so it raises `RunCancelled` once the
worker is cancelled, and marshals `TrialEvent`s onto the UI thread as
messages. The same hook is what the dashboard WebSocket
(`ConnectionManager.broadcast_event`) needs.
