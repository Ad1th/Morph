# Morph Demo Apps

Controlled failure fixtures used to demonstrate Morph's capture -> reproduce -> experiment ->
isolate -> fix -> replay loop. See [docs/faultyapps.md](../docs/faultyapps.md) for the full
design rationale, tuning guidance, and environment-knob commands.

Every app exposes the same CLI contract:

```
python -m apps.<name> run            # human-readable, exit 0 (pass) / 1 (engineered failure) / 2 (setup error)
python -m apps.<name> test            # machine mode: last stdout line is a JSON result object
python -m apps.<name> run --fixed     # runs the fixed variant
```

`test` JSON line: `{"result": "pass|fail", "signal": "...", "duration_ms": N, "detail": "..."}`

## Apps

| App | Trigger | Baseline | Under condition | Classification |
|---|---|---|---|---|
| [timeout](timeout/) | network latency on `lo` | 0/50 | 20/20 fail | environment-caused |
| [locale_parse](locale_parse/) | `LANG` / `LC_NUMERIC` | 0/50 | 50/50 fail | environment-caused |
| [race](race/) | CPU quota (cgroup `cpu.max`) | 0/50 | 50/50 fail, rate 0.31-0.42 | environment-**exposed** |
| pool_retry (flagship) | latency **+** packet loss combined | — | — | **not landed yet, see below** |
| real/turkish_locale | `LANG=tr_TR.UTF-8` (JVM) | — | — | not built yet |

### Failure B is still being tuned

The flagship interaction fixture is written but does **not** yet meet the
[§7 acceptance table](../docs/faultyapps.md#7-manual-verification-protocol), so it
is deliberately not merged. Latest measurement:

| leg | target | measured |
|---|---|---|
| baseline | < 5% | 0% ✓ |
| latency alone | < 15% | 0% ✓ |
| loss alone | < 15% | 20% ✗ |
| latency + loss | > 90% | 80% ✗ |
| `--fixed` under both | < 5% | 13% ✗ |

The `--fixed` leg is the blocking one: the fix must survive the exact condition
that breaks the app, or the fix → replay → PASS step of the demo does not hold.

Root cause is understood — a request dies when *every* attempt stalls, with
probability `stall_rate ^ (retries + 1)`, and no pool size can prevent that. The
open question is a parameter set where retries are high enough to make exhaustion
negligible while the combination still cascades past the deadline on elapsed time
(so the failure mechanism stays the documented one).

Per [faultyapps.md §9](../docs/faultyapps.md#9-build-order-and-review-1-target),
A + D + C is a viable Review 1 without it.

## Verification status

Every app's failure logic, baseline, and fix are verified. What is **not** yet
verified anywhere is that the *real* OS-level knobs produce these results — all
measurements so far use each app's simulation knob, because this machine has no
`tc`, no Clumsy admin rights, and no cgroups.

| Condition | Verified via | Still needs |
|---|---|---|
| network latency | server-side delay | real `tc netem` / Clumsy / `dnctl` |
| packet loss | server-side stall probability | real `tc netem` — and recalibration, see below |
| CPU quota | interpreter switch interval | real cgroup `cpu.max` on the Pi |
| locale | real `setlocale` | nothing — genuinely verified |

Two calibration warnings for whoever runs these against real shaping:

- **`netem loss 2%` is not `MORPH_B_SIM_STALL_PCT=2`.** Real loss costs a TCP
  retransmit timeout rather than losing a request, and one HTTP request is many
  packets. The simulated value is a per-*request* stall probability.
- **Loopback doubles latency.** `netem delay 180ms` on `lo` delays request *and*
  response, so RTT grows ~360ms. The netem parameter is roughly half the RTT.

[PRD §39](../docs/Morph_PRD.md) makes this the demo's single point of failure, so
this verification pass is the highest-value remaining work on the corpus.

Install demo-app deps separately from Morph's own deps:

```bash
pip install -r apps/requirements.txt
```
