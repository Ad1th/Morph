# `morph tui` — the live console

A full-screen terminal app (Textual) for running experiments and watching them
resolve. Runs anywhere a terminal does; also servable in a browser with
`textual serve "morph tui"`.

```
morph tui           # live
morph tui --demo    # replay a recorded experiment (no root / network / target app)
python -m morph.tui
```

## Home

Four ways in, keyboard-first. `e` Experiment · `t` Threshold · `n` Environment ·
`r` Regressions · `esc` back · `F2` light/dark · `Ctrl+P` command palette.

## Experiment — causal isolation

Enter a target profile (or leave blank for *this host + latency/loss*), a
command, and a trial count, then `Run`. Each condition gets a **lane**:

- trials land one by one, green pass / red fail, with a live failure-rate bar;
- when a batch completes, its Fisher's-exact **p-value** and effect appear and a
  `SIGNIFICANT ↑` stamp lands — the p-value is only ever computed once, over the
  whole fixed-size batch (no sequential peeking);
- the app border pulses when significance is reached;
- the right pane streams the target's stdout/stderr.

When every condition has run, the **verdict card** states the diagnosis in plain
language — `ENVIRONMENT-CAUSED` / `ENVIRONMENT-EXPOSED` / `APPLICATION BUG` /
`NO EFFECT` — and, for a latency+loss target, a **2×2 interaction matrix**
resolves from the same four batches: three cells green, "both" red.

## Threshold — failure boundary

Pick a parameter (`network.latency_ms` / `network.packet_loss_percent`), a
range, and a command. The **gauge** shows a green *known-safe* / red
*known-failing* track with a yellow uncertainty band between the `[safe]` and
`[fail]` markers; every probe narrows the band and a `▲` locks onto the boundary
estimate.

## Environment — capture / shape / reconcile

Captures this host, then lets you pick a template (host / high-latency /
constrained / raspberry-pi-ish), edit numeric fields inline, and load/save
profile JSON. **Reconcile** stamps every field `REPRODUCED` / `APPROXIMATED` /
`UNAVAILABLE` for the current host.

## Regressions — flight recorder

Lists `.morph/regressions/` bundles. **Replay** re-runs the selected bundle
under its recorded environment, live, then shows `REGRESSION LOCKED` /
`REGRESSION OPEN` against its tolerance. **Export CI test** writes the standalone
pytest invariant.

## How it's wired

The engine takes an optional `on_event(TrialEvent)` callback
(`morph/schema/events.py`) threaded through `run_trials → isolate_variables →
detect_interaction → run_experiment → search_threshold`. `morph/tui/orchestrator.py`
builds `RunResult`-returning trial runners and drives the engine; each screen
runs that in a Textual thread worker and marshals `TrialEvent`s onto the UI
thread as messages. The same hook is what the dashboard WebSocket
(`ConnectionManager.broadcast_event`) needs.
