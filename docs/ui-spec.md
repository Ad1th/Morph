# Morph: UI & Parameter-Control Spec

> The buildable design spec. Every parameter → its control type, range, unit, default, step. Every screen → its components and states. Complements [Morph_Design_Spec.md](./Morph_Design_Spec.md) (visual intent, immersion, motion): this doc is the concrete "what widget, what numbers" layer.

Derived from: [Environment Parameter Specification](../Morph_Environment_Parameters_Specification%20(1).pdf), [PRD](./Morph_PRD.md), [Design Spec](./Morph_Design_Spec.md), [Architecture](./architecture.md), [Faulty Apps](./faultyapps.md).

---

## Contents

1. [Control-type vocabulary](#1-control-type-vocabulary)
2. [Parameter control catalog: MVP](#2-parameter-control-catalog-mvp)
3. [Parameter control catalog: Phase 2](#3-parameter-control-catalog-phase-2)
4. [Connection-type presets](#4-connection-type-presets)
5. [Cross-field validation rules](#5-cross-field-validation-rules)
6. [Per-field state & platform badges](#6-per-field-state--platform-badges)
7. [The Parameter Configuration panel](#7-the-parameter-configuration-panel)
8. [Experiment controls](#8-experiment-controls)
9. [Screen inventory](#9-screen-inventory)
10. [Component inventory & states](#10-component-inventory--states)
11. [Visualisation specs](#11-visualisation-specs)
12. [Units, formatting, number-input rules](#12-units-formatting-number-input-rules)
13. [Colour & status semantics](#13-colour--status-semantics)
14. [Motion](#14-motion)
15. [Responsive & accessibility](#15-responsive--accessibility)
16. [Design priority order](#16-design-priority-order)

---

## 1. Control-type vocabulary

| Control | Use for | Notes |
|---|---|---|
| **Slider + linked number field** | Continuous numeric params with a wide range (latency, RAM, bandwidth) | Slider for feel, number field for exact values: threshold demos need "153 ms" typed precisely. Both always visible, kept in sync. |
| **Log-scale slider** | Params spanning 3+ orders of magnitude (latency 0–5000, bandwidth 0.1–1000, RAM 256–16384) | Linear sliders waste 90% of travel on the boring high end. Tick marks show the scale. |
| **Segmented control** | Small discrete sets (CPU cores 1/2/4/8, case sensitivity) | Faster than a slider for ≤6 options. "Custom…" chip opens a stepper if more range is needed. |
| **Number stepper** | Integer limits with a host default (max processes, thread limit, FD limit) | Shows the detected host value greyed as the placeholder/default. |
| **Toggle** | Binary state (offline/online, read-only FS, unlimited bandwidth, enable time override) | A disabled toggle for a param that needs a worker still shows, with a ☁ badge. |
| **Searchable dropdown (combobox)** | Large enumerations (locale, timezone, filesystem type, OS) | Type-ahead filter, grouped options, "custom…" free-text at the bottom. |
| **Key–value row editor** | Environment variables | Repeatable rows: name + value + remove; "Add variable" button; duplicate-key warning. |
| **Range mini-form (from / to / step)** | A parameter switched into "sweep" mode by the experiment engine | Replaces the single value control inline. Also accepts a discrete point list. |
| **Datetime picker** | System-time override | Paired with an enable toggle; when off, shows "live". |

Every numeric control also carries: current value, unit, reset-to-default affordance, a **Hold / Vary** toggle (section 8), a state chip (section 6), and a platform badge (section 6).

---

## 2. Parameter control catalog: MVP

Host = the machine Morph runs on (e.g. the M3 Air: 8 logical CPUs, 16 GiB). "> host ⇒ worker" means values above the host capability are allowed in the UI but flip the run target to a Pi/cloud worker and show a ☁ badge.

| Param | Control | Unit | Min | Max | Default | Step / scale | Snap marks | Notes |
|---|---|---|---|---|---|---|---|---|
| **CPU cores** | Segmented (1 · 2 · 4 · 6 · 8 · Custom) → stepper | count | 1 | host logical CPUs (> host ⇒ worker) | host count | 1 | 1, 2, 4, 6, 8 | Constrains the app to N cores via cgroup cpuset / affinity. |
| **CPU quota** (usage limit) | Slider + number | % of one CPU | 1 | cores × 100 | cores × 100 (unthrottled) | 1 below 20 %, 5 above | 10, 25, 50, 100, 200, 400 | The knob Failure C (race) uses; fine control in the 1 to 20 % band matters. Enforced only via cgroup `cpu.max` on Linux with root or a delegated cgroup; on macOS/Windows it is an env hint and the row must show `UNAVAILABLE` / ☁. |
| **RAM limit** | Log slider + preset dropdown + number | MiB | 256 | host RAM (> host ⇒ worker) | host RAM | snap to 256 / 512 / 1024 / 2048 / 3072 / 4096 / 6144 / 8192 / 12288 / 16384 | those | Below ~256 MiB most runtimes won't start: warn. |
| **Network latency** | Log slider + number | ms (round-trip) | 0 | 5000 | 0 | 1 (0 to 50) · 5 (50 to 200) · 25 (200 to 1000) · 100 (1000 to 5000) | 20, 50, 100, 200, 500, 1000, 2000 | The single most-used control. The value is an RTT (the proxy adds half per direction). Interesting band is 40 to 300 ms; give it the most travel. |
| **Packet loss** | Slider + number | % | 0 | 30 | 0 | 0.1 (0 to 2) · 0.5 (2 to 10) · 1 (10 to 30) | 1, 2, 5, 10, 20 | Loss is delivered as a retransmission stall, `max(200 ms, 3 × RTT)`, never corruption. The flagship operating point is 120 ms / 18 %. |
| **Bandwidth** | Log slider + number + **Unlimited** toggle | Mbit/s | 0.1 | 1000 | Unlimited (toggle on, slider disabled) | log: 0.1 · 0.25 · 0.5 · 1 · 2 · 5 · 10 · 25 · 50 · 100 · 250 · 500 · 1000 | 1, 10, 100 | Turning the toggle off enables the slider. |
| **Jitter** | Slider + number | ms | 0 | 500 (**and ≤ latency**) | 0 | 1 (0 to 50) · 5 (50 to 500) | 10, 25, 50, 100 | **Phase 2 control.** The proxy supports `jitter_ms` and the profile schema carries `network.jitter_ms`, but the controller does not pass it to the adapters yet; render disabled with a "not applied" hint until it does. |
| **Locale** | Searchable dropdown + custom | BCP-47 | n/a | n/a | host locale | n/a | n/a | Curated list (en-US, en-IN, en-GB, de-DE, fr-FR, tr-TR, pt-BR, ja-JP, zh-CN, ar-SA, es-ES, ru-RU) + custom. **Shows a ⚠ badge if the tag isn't installed on the target runtime** (the Pi ships almost none). |
| **Timezone** | Searchable dropdown (IANA, grouped by region) + custom | IANA name | n/a | n/a | host tz | n/a | n/a | Show the current UTC offset beside the selection. |

---

## 3. Parameter control catalog: Phase 2

Design the panel to accommodate these now (same row anatomy); build the controls when the adapters land.

| Param | Control | Unit | Min | Max | Default | Step / scale | Notes |
|---|---|---|---|---|---|---|---|
| **Memory pressure** | Slider + number | % of limit pre-consumed | 0 | 95 | 0 | 5 | Balloons memory inside the limit before the app starts. |
| **Swap** | Toggle + slider | MiB | 0 | 8192 | off | 256 | Toggle enables the size slider. |
| **CPU architecture** | Dropdown | n/a | n/a | n/a | host arch | n/a | Worker selector (x86_64 / arm64 / …). ≠ host ⇒ ☁ badge, no local control. |
| **OS** | Dropdown | n/a | n/a | n/a | host OS | n/a | macOS / Windows / Linux. Worker selector. |
| **OS version** | Dependent dropdown | n/a | n/a | n/a | host | n/a | Options depend on the OS choice. Worker selector. |
| **Kernel version** | Dropdown / text | n/a | n/a | n/a | host | n/a | Worker selector; mostly metadata. |
| **System time override** | Datetime picker + enable toggle | ISO 8601 | n/a | n/a | off ("live") | 1 min | libfaketime / `TZ`+offset shim. |
| **Clock offset** | Slider + number | seconds | −172800 | +172800 | 0 | 1 (fine) · 60 · 3600 | Marks at ±1 h, ±1 d. |
| **Time speed** | Log slider + number | × | 0.1 | 10 | 1 | log | Marks 0.5 / 1 / 2 / 5. libfaketime rate. |
| **Filesystem type** | Dropdown | n/a | n/a | n/a | host fs | n/a | ext4 / xfs / btrfs / APFS / NTFS / FAT32. Loopback-image or worker. |
| **Disk read latency** | Slider + number | ms/op | 0 | 100 | 0 | 0.5 (0–10) · 5 (10–100) | Marks 1 / 5 / 10 / 25. |
| **Disk write latency** | Slider + number | ms/op | 0 | 100 | 0 | 0.5 (0–10) · 5 (10–100) | n/a |
| **Disk space limit** | Log slider + number | MiB | 100 | host free | host free | log | Marks 512 / 1024 / 4096. Loopback image / quota. |
| **Read-only filesystem** | Toggle | n/a | n/a | n/a | off | n/a | Mount target dir read-only. |
| **Case sensitivity** | Segmented (Sensitive · Insensitive) | n/a | n/a | n/a | host behaviour | n/a | Needs a case-toggled FS image or a worker. |
| **Environment variables** | Key–value row editor | n/a | n/a | n/a | empty (overlaid on host env) | n/a | Duplicate-key + reserved-name (`PATH`, `HOME`) warnings. |
| **Process timeout** | Enable toggle + slider + number | s | 1 | 3600 | off | 1 (1–60) · 10 (60–600) · 60 (600–3600) | Kills the run after N s. Marks 5 / 30 / 60 / 300. |
| **Max processes** | Number stepper | count | 1 | 4096 | host default (shown greyed) | 1 | `ulimit -u`. |
| **Thread limit** | Number stepper | count | 1 | 10000 | host default | 1 | n/a |
| **File descriptor limit** | Number stepper | count | 64 | 1048576 | host default | 1024-ish increments | `ulimit -n`. Marks 1024 / 4096 / 65536. |
| **Network availability** | Toggle (Online · Offline) | n/a | n/a | n/a | Online | n/a | Offline **disables** latency / bandwidth / loss / jitter (greyed). |
| **Connection type** | Dropdown (preset bundle) | n/a | n/a | n/a | none | n/a | Selecting one fills the four network sliders: section 4. |

---

## 4. Connection-type presets

Selecting a preset writes these into the network controls and tags each as "from preset · <name>"; the user can then tweak any of them (which retags it "modified").

| Preset | Latency | Bandwidth | Packet loss | Jitter |
|---|---|---|---|---|
| Fiber | 5 ms | 500 Mbit/s | 0 % | 1 ms |
| Cable | 15 ms | 100 Mbit/s | 0.1 % | 3 ms |
| 4G / LTE | 60 ms | 25 Mbit/s | 0.5 % | 15 ms |
| 3G | 150 ms | 3 Mbit/s | 1.5 % | 40 ms |
| 2G / EDGE | 400 ms | 0.2 Mbit/s | 3 % | 80 ms |
| Satellite | 600 ms | 20 Mbit/s | 1 % | 30 ms |
| Public / airport Wi-Fi | 120 ms | 5 Mbit/s | 2 % | 60 ms |

---

## 5. Cross-field validation rules

The panel enforces these live (block or warn, never silently clamp without telling the user):

- **Jitter ≤ latency.** Jitter slider max tracks the current latency; jitter disabled when latency = 0.
- **CPU quota ≤ cores × 100 %.** Lowering cores lowers the quota ceiling.
- **RAM / cores / disk space > host capability** ⇒ run target auto-switches to worker, ☁ badge on the field and on the run button. If no worker is configured, the run button is disabled with "needs a worker for: RAM 24 GiB".
- **Locale not installed on target** ⇒ ⚠ badge + "will fall back to C locale" note; still runnable.
- **Timezone requires tzdata** ⇒ ⚠ if missing on target.
- **Network availability = Offline** ⇒ latency / bandwidth / loss / jitter greyed and ignored.
- **Bandwidth Unlimited toggle on** ⇒ bandwidth slider disabled.
- **Enable toggles off** (swap, process timeout, system-time override) ⇒ their sliders disabled and excluded from the profile.
- **macOS host + CPU quota / memory limit / FS type / case sensitivity** ⇒ ⚠ "not controllable on macOS: routes to a Linux worker" (matches the PRD platform-honesty rule). A worker is used only with an explicit `--cloud` / "Run on worker" action, never silently.

---

## 6. Per-field state & platform badges

Every parameter row shows **two** small indicators. These are core to Morph's credibility: the UI must never imply something was reproduced when it wasn't ([Design Spec §8, §17, §27](./Morph_Design_Spec.md)).

### State chip (what Morph did with this value)

| Chip | Meaning | Colour |
|---|---|---|
| `DETECTED` | Read from the captured/host environment | neutral |
| `REQUESTED` | User set a target value; not yet applied | accent outline |
| `REPRODUCED` | Applied exactly on the run target | green |
| `APPROXIMATED` | Applied, but not exactly (e.g. a non-IANA `TZ` name; bandwidth through the proxy's token bucket) | amber |
| `UNAVAILABLE` | Could not be applied at all this run | red outline |

### Platform badge (whether Morph *can* control this here)

| Badge | Meaning |
|---|---|
| ✓ local | Controllable on the current host |
| ≈ approx | Controllable but only approximately on this host |
| ☁ worker | Requires a Pi / cloud worker |
| ✕ unsupported | Not controllable anywhere in the current build |

Both are driven by the parameter **metadata model** (`GET /parameters`, [Env Param Spec §5](../Morph_Environment_Parameters_Specification%20(1).pdf)): `detectable`, `controllable`, `experimentable`, `platform_support`, `min`, `max`, `default`, `unit`. After a run, the chip comes from the `RunResult.fidelity` map the adapter returned (`status`, `mechanism`, `detail` per field), so the UI shows what was actually done, not what was asked. The frontend renders entirely from this metadata: adding a parameter later is a metadata entry, not new UI code.

---

## 7. The Parameter Configuration panel

The screen where the user builds/edits a target environment before **ENTER ENVIRONMENT** ([Design Spec §17](./Morph_Design_Spec.md)).

### Layout

- **Grouped accordions**, collapsed by default except Network: `Network` · `CPU & Memory` · `Locale & Time` · `Filesystem` · `Process / Runtime` · `Environment variables`. Group header shows a count of non-default params inside.
- Each group = a stack of **parameter rows**. Row anatomy, left → right:
  `[label + tooltip] [Hold/Vary toggle] [control (slider+number / dropdown / toggle)] [unit] [state chip] [platform badge] [reset ↺]`
- **Sticky summary bar** at top: compact readout of every non-default param (`4 cores · 8 GiB · 180 ms · 2 % loss · en-IN · Asia/Kolkata`): this is the same string shown on environment cards and in the diff view, so it must be generated by one shared formatter.
- **Actions** (sticky footer): `Reset to host` · `Load from captured profile…` · `Save as profile…` · **`ENTER ENVIRONMENT`** (primary).

### Behaviours

- Changing any value sets its chip to `REQUESTED` and enables the primary button.
- `Reset to host` returns everything to detected values, chips back to `DETECTED`.
- A row whose platform badge is ☁ or ✕ still lets you set a value (it goes in the profile) but annotates the primary button.
- Search/filter box at the top of the panel filters rows by name across all groups.

### States

`empty` (fresh, all host defaults) · `editing` · `has-worker-requirement` (primary button annotated) · `invalid` (a hard rule violated, primary disabled, offending row flagged) · `loading-from-profile` · `applied` (post-run, chips show REPRODUCED/APPROXIMATED/UNAVAILABLE).

---

## 8. Experiment controls

### Hold / Vary toggle (per parameter)

Every numeric parameter row has a two-state toggle:

- **Hold** (default): the single value control is shown; the value is fixed for all trials.
- **Vary**: the single control is replaced inline by a **sweep mini-form**:
  - Mode: `Range` (from · to · step) or `Points` (comma list, e.g. `0, 100, 150, 200, 250`)
  - For `Range`: three small number fields, validated against the param's min/max/step from metadata
  - A live preview chip: "7 values: 0, 50, 100, 150, 200, 250, 300"

Only parameters whose metadata has `experimentable: true` can be set to Vary.

### Experiment run configuration (panel above the results)

| Control | Type | Range | Default | Notes |
|---|---|---|---|---|
| Mode | Segmented (Sequential · Batch) | sequential · batch | Sequential | **Sequential** (default): paired round-robin trials with an anytime-valid e-value per candidate and early stopping; safe to watch live. **Batch**: fixed N per condition, one-sided Fisher with Holm correction at the end; only honest if nobody stops early. `ExperimentConfig.mode`. |
| Round budget (sequential) / Trials per condition (batch) | Slider + number | 3 to 60 rounds / 3 to 500 trials | 12 rounds / 5 trials | A round is one baseline trial plus one per candidate. Show estimated wall-clock. |
| Alpha | Number | 0.001 to 0.2 | 0.05 | The e-value bar is K/alpha for K candidates (family-wise); in batch mode the Holm level. Show as "advanced". |
| Baseline condition | Read-only summary | n/a | all params at host/normal | The control group. |
| Stop early if conclusive | Toggle | n/a | on (sequential only) | A candidate stops consuming trials once its e-value reaches the bar. In batch mode the toggle is disabled with the reason. |
| Combination testing | Toggle | n/a | off | After single-variable legs, also run the 2x2 (`neither`, A, B, A+B) and report `interaction_confirmed` (Failure B story). |
| Minimal condition set | Button | n/a | off | Run ddmin over the deviating fields (`POST /minimize`); shows the 1-minimal set and the oracle calls. |

### Variable-isolation view

A matrix: rows = candidate conditions (each swept param + flagged combinations), columns = `Trials · Failures · Failure rate · Δ risk (95 % CI) · E-value (pairs) · p · Verdict`. The row where the rate jumps is highlighted. This is the "watch variables get eliminated" moment ([Design Spec §25 to 26](./Morph_Design_Spec.md)).

**What may be shown live.** Every engine step arrives as a `TrialEvent` (`morph/schema/events.py`) over `/ws/experiment/{id}`: `phase_start`, `condition_start`, `trial`, `condition_done`, `comparison`, `evidence`, `search_probe`, `verdict`, `phase_done`. A `trial` event never carries a p-value. The **only** statistic safe to stream live is the `evidence` event's `e_value` (with `evidence_threshold`, `pairs`, `decisive`), because it is anytime-valid: the UI may animate it climbing toward the bar and mark the row **decisive** the moment it crosses. Fisher p-values appear once, on `comparison` / `verdict`, and in sequential mode they are labelled as the final-batch reference number, not the decision.

---

## 9. Screen inventory

Condensed from [Design Spec §14–41](./Morph_Design_Spec.md). For each: purpose · key components · states.

| # | Screen | Key components | States |
|---|---|---|---|
| 1 | **Home / overview** | Recent-environments list, quick-stat row (envs / experiments / open failures), "what needs attention" | empty (no envs) · populated · a run in progress |
| 2 | **Environment library** | Environment cards (OS glyph, summary string, metric bars, capture date), "New environment", filter | empty · list · card hover · card selected |
| 3 | **Environment detail** | Full param readout grouped, capture metadata, **ENTER ENVIRONMENT** primary, "Edit parameters" | captured (read-only) · draft (editable) · applied |
| 4 | **Parameter configuration panel** | Section 7 in full | Section 7 states |
| 5 | **OS-adaptive workspace** (Win / mac / Linux) | Workspace chrome, app window, terminal, run controls, subtle target-OS label | idle · preparing · running · failed · reproduced · passed |
| 6 | **Preparing-environment transition** | Checklist ("Applying: CPU ✓ Memory ✓ Network ✓ Locale ✓ Filesystem ✓ → Starting app…") | each item pending / ok / approximated / failed |
| 7 | **Run + telemetry** | Live metric strip (CPU %, mem, latency, req duration), log view, run-state pill | streaming · finished-pass · finished-fail · crashed |
| 8 | **Experiment: baseline vs treatment** | Two condition cards (CONTROL / TREATMENT) each with trials/failures/result, confidence indicator (conclusion first, stats expandable) | running · conclusive · inconclusive |
| 9 | **Experiment: variable isolation** | The isolation matrix (section 8), sweep config, trial-count control | sweeping · complete |
| 10 | **Threshold search** | Probe dots on a value axis, the posterior density strip, the **credible interval** band (`credible_low` to `credible_high`, 90 % mass) with the posterior median marked, the dose-response curve, and the resulting sentence ("fails when latency exceeds ~42 ms, 90 % credible 38 to 47 ms"). Method chip: `probabilistic_bisection` (default) or `bisection`. | searching · boundary_found · never_fails · always_fails · inconclusive |
| 11 | **Root cause view** | Root-cause card (primary condition, threshold with credible interval, interaction: confirmed/none, minimal condition set), evidence table, **CAUSED / EXPOSED / INTERNAL / INCONCLUSIVE** label (`environment_caused` / `environment_exposed` / `application_internal` / `no_effect`), "Create regression test" | caused · exposed · internal · inconclusive |
| 12 | **Environment diff** | Two columns (Your machine / Target), only differing rows shown, delta highlighted | n/a |
| 13 | **Regression test: create** | Prefilled trigger (env + command), expected outcome, name field, save | draft · saved |
| 14 | **Regression test: library** | Rows (name, env summary, trigger, last result, created, build ref) | empty · list · a test failing |
| 15 | **CI view** | Build header, regression checklist with ✓/✕, pass count | passing · failing · running |
| 16 | **Cloud / worker routing** | "Cannot reproduce locally: RAM 24 GiB" → [Run on worker], worker status | local-sufficient · needs-worker · worker-running · worker-unavailable (fallback note) |
| 17 | **Live demo mode** | Stripped, linear stepper through the 8-step demo ([PRD §39](./Morph_PRD.md)) | one state per step |
| 18 | **Landing page** | Immersive scroll sequence: see [Design Spec §8–13](./Morph_Design_Spec.md); no parameter controls | scroll progress; fallback (pre-rendered) variant |

---

## 10. Component inventory & states

Build these as a small system early ([Design Spec §52](./Morph_Design_Spec.md)). Each must support every listed state.

| Component | States |
|---|---|
| **Parameter slider** (+ linked number field) | default · hover · focus · dragging · at-min · at-max · disabled · sweeping (replaced by mini-form) · value-from-preset · approximated (amber tick) |
| **Number field** | default · focus · invalid (out of range / wrong step) · disabled |
| **Segmented control** | default · selected · disabled-option · custom-expanded |
| **Number stepper** | default · at-limit · host-default-placeholder · disabled |
| **Toggle** | on · off · disabled · disabled-with-worker-badge |
| **Searchable dropdown** | closed · open · typing/filtering · no-results · custom-entry · warning (locale not installed) |
| **Key–value row** | default · duplicate-key warning · reserved-name warning · being-removed |
| **Sweep mini-form** | range mode · points mode · invalid · preview |
| **Hold / Vary toggle** | hold · vary · vary-disabled (not experimentable) |
| **State chip** | detected · requested · reproduced · approximated · unavailable |
| **Platform badge** | local · approx · worker · unsupported |
| **Environment card** | default · hover · selected · running · last-result-pass · last-result-fail · inconclusive |
| **Metric bar** (CPU/RAM/net mini-viz) | idle · live-updating · over-limit |
| **Diff row** | unchanged (hidden by default) · changed (delta highlighted) |
| **Experiment matrix row** | pending · running · pass · fail · highlighted-transition |
| **Confidence indicator** | high · medium · inconclusive · (expanded: stats detail) |
| **Root-cause card** | caused · exposed · inconclusive |
| **Run-state pill** | idle · preparing · running · failed · reproduced · passed · inconclusive |
| **Preparing checklist item** | pending · ok · approximated · failed |
| **Terminal** | idle · streaming · finished |
| **Log row** | info · warn · error · expanded |
| **Regression card** | passing · failing · never-run |
| Toast · Modal · Nav · Tabs · Table | standard |

---

## 11. Visualisation specs

- **Experiment matrix (isolation):** plain table, monospace numerals, columns `Condition · Trials · Failures · Rate · Δ vs baseline · Verdict`. The transition row gets a left accent bar and a bolder rate. No bar charts inside cells: keep it scannable ([Design Spec §25](./Morph_Design_Spec.md)).
- **Threshold chart:** x = swept value (log axis if the param is log-scale), y = failure probability 0 to 100 %. Draw the `dose_response` curve (posterior-mean P(fail | x)) as the line, each `search_points` probe as a dot at 0 or 1, the `posterior` density as a strip under the axis, and the credible interval as the shaded vertical band with the median as a tick. `outcome` drives the caption: `boundary_found` gives the sentence; `never_fails` / `always_fails` say so plainly and draw no band; `inconclusive` shows the three posterior probabilities (`probability_boundary_in_range`, `probability_never_fails`, `probability_always_fails`). Also show `floor_failure_rate` / `ceiling_failure_rate` as "flakiness learned: 3 % below, 92 % above". Keep it one small chart, not a dashboard.
- **Baseline vs treatment:** two side-by-side cards, big number = failure rate, small = `n failures / N trials`. Conclusion text on top ("Network conditions strongly associated with failure: high confidence"), the detail in a collapsible under it: in sequential mode `E = 102 after 9 pairs, anytime p = 0.0098, stopped early`; in batch mode `one-sided Fisher p = 0.001, Holm-adjusted 0.003`; always the risk difference with its 95 % Newcombe interval. Never lead with the statistic.
- **Environment diff:** two columns, only differing rows rendered, the changed value in the target column carries the delta (`8 GiB → 4 GiB`), colour only as a secondary cue (also an icon/weight change) for accessibility.
- **Metric strip (during run):** 4–6 sparklines max (CPU %, mem, latency, req duration, error count). Small, top of the workspace, not the focus.
- **Confidence:** three-state word + dot (High / Medium / Inconclusive), expandable to `E = 102 (bar 60) · 9 pairs · baseline 0/12 · treatment 9/9` or, in batch mode, `Fisher exact p = 0.001 · baseline 2/100 · treatment 71/100`.
- **Root cause card:** the four-way verdict, `environment_caused` / `environment_exposed` / `application_internal` / `no_effect` (the last is what the UI shows as INCONCLUSIVE), the strongest condition, `interaction_confirmed` when the 2x2 ran, and the ddmin minimal set when `morph minimize` ran.

---

## 12. Units, formatting, number-input rules

- **Latency / jitter / disk latency:** `ms`, integer display, allow one decimal on input.
- **Packet loss:** `%`, one decimal, `0.0`–`30.0`.
- **Bandwidth:** `Mbit/s`; show `Unlimited` as text when the toggle is on.
- **RAM / disk:** binary units, `MiB` under 1024, `GiB` at/above, one decimal for GiB (`7.5 GiB`).
- **CPU cores:** bare integer. **CPU quota:** `%` with the equivalent shown as a hint (`50 % ≈ 0.5 CPU`).
- **Clock offset:** signed, largest sensible unit (`+2 h`, `−30 s`, `+1 d 3 h`).
- **Time speed:** `×` with one decimal (`0.5×`, `2.0×`).
- Number fields: reject out-of-range on blur (snap to nearest valid + brief toast "clamped to max 5000 ms"), reject non-step values by rounding to the nearest step, show the unit as a suffix inside the field.
- The **summary string** (`4 cores · 8 GiB · 180 ms · 2 % loss · en-IN · Asia/Kolkata`) is produced by one shared formatter used on cards, the panel summary bar, the diff view, and regression rows. Order: CPU, RAM, latency, loss, bandwidth, jitter, locale, timezone, then others. Omit params at default.

---

## 13. Colour & status semantics

One accent colour, used sparingly (active control, transition band, primary button, confirmed finding). Everything else neutral graphite ([Design Spec §5–6](./Morph_Design_Spec.md)).

| Semantic | Colour | Also encoded as (accessibility) |
|---|---|---|
| Reproduced / pass / fixed | green | ✓ icon, `PASS` label |
| Approximated / inconclusive / warning | amber | ≈ icon, `APPROX` / `INCONCLUSIVE` label |
| Failure / reproduced failure | red | ✕ icon, `FAIL` label |
| Requested (pending apply) | accent outline | dashed border |
| Informational / detected | neutral | n/a |

Status is **never** conveyed by colour alone: always an icon or a text label too.

---

## 14. Motion

Purposeful only ([Design Spec §57](./Morph_Design_Spec.md)):

- Environment enter / OS switch: the signature transition.
- Preparing-environment checklist ticking through.
- Slider drag → the summary bar value updating in place.
- Experiment matrix rows resolving pass/fail as trials complete.
- Threshold band settling once found.
- Root-cause reveal.

No ambient motion, no per-card animation, no decorative particles. Respect `prefers-reduced-motion` (cut everything except instant state swaps).

---

## 15. Responsive & accessibility

- **Primary widths:** 1440 / 1600 / 1920. Laptop (1280) must work. **No mobile**: don't spend time on it ([Design Spec §51](./Morph_Design_Spec.md)).
- The parameter panel: two-column groups at ≥1600, single column below.
- **Sliders:** keyboard operable (arrow = step, shift+arrow = 10×step, home/end = min/max), visible focus ring, the linked number field is the accessible fallback for exact entry.
- **Contrast:** meet WCAG AA on text and on the graphite-on-near-black surfaces.
- **Focus order** follows visual order within each parameter row and group.
- Terminal / log / numeric readouts in a readable monospace at ≥13px.

---

## 16. Design priority order

Ties to the hackathon schedule ([PRD §29–35](./Morph_PRD.md)). Do **not** reorder: a beautiful landing page on a weak product loses.

1. **Component system foundations**: slider+number, toggle, dropdown, segmented, state chip, platform badge, run-state pill. (Hours 0–2)
2. **Parameter configuration panel** (section 7) with the **MVP params only** (section 2). This is the screen a judge will scrutinise. (Hours 2–5)
3. **OS-adaptive workspace** shell + preparing-environment checklist + run/telemetry. Windows and macOS full; Linux simplified ([Design Spec §19–20](./Morph_Design_Spec.md)). (Hours 5–8)
4. **Experiment views**: baseline vs treatment, variable isolation matrix, threshold chart. This is where the technical-depth points are. (Hours 8–11)
5. **Root cause view** + CAUSED/EXPOSED/INCONCLUSIVE + environment diff. (Hours 11–14)
6. **Regression create + library**, **CI view**. (Hours 14–16)
7. **Live demo mode**: the linear stepper. (Hours 16–17)
8. **Landing page**: immersive if time allows, pre-rendered fallback by hour 5–6 decision point. (Hours 17–21)
9. Polish, empty/error states, motion pass. (Hours 21–24)

Phase-2 parameters (section 3) get their controls only once their runtime adapters exist: the panel is already built to hold them.
