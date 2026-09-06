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
| [pool_retry](pool_retry/) (flagship) | latency **+** packet loss combined | 0/20 | 19/20 fail | environment-caused, **interaction** |
| real/turkish_locale | `LANG=tr_TR.UTF-8` (JVM) | — | — | not built yet |

### Failure B, the interaction fixture

Verified against the [§7 acceptance table](../docs/faultyapps.md#7-manual-verification-protocol)
under **real** injected conditions, 20 trials per leg:

| leg | target | measured |
|---|---|---|
| baseline | < 5% | 0/20 ✓ |
| latency alone (90ms) | < 15% | 0/20 ✓ |
| loss alone (12%) | < 15% | 1/20 ✓ |
| latency + loss | > 90% | **19/20** ✓ |
| `--fixed` under both | < 5% | 0/20 ✓ |

Neither condition alone breaks it; together they do, and the one-line fix
survives the exact condition that breaks the app.

## Verification status

Every app's failure logic, baseline, and fix are verified. How the *condition*
was applied differs per app, and that distinction matters — a simulated knob
proves the app's logic, not that the environment can actually drive it.

| App | Condition applied by | Still needs |
|---|---|---|
| pool_retry (B) | **real** — morph's TCP proxy, genuine delay and chunk drops | `tc netem` cross-check |
| locale_parse (D) | **real** — `setlocale` | nothing |
| timeout (A) | simulated — server-side delay | real injection; the proxy can now do this |
| race (C) | simulated — interpreter switch interval | real cgroup `cpu.max` on the Pi |

**Latency is applied per direction**, both through the proxy and through `netem`
on loopback, so round-trip is ~2x the configured value: `90ms` is ~180ms RTT.
Any threshold Morph reports will be about twice the parameter that was dialled
in unless it corrects for this.

Remaining work, highest value first:

1. **Run Failure A through the proxy.** B already proves the mechanism works and
   needs no admin rights, so A's simulated delay can be replaced with real
   injected latency the same way. This closes [PRD §39](../docs/Morph_PRD.md)'s
   single point of failure on the machine you already have.
2. **Failure C on the Pi**, under a real cgroup quota — the one condition the
   proxy cannot supply.

Install demo-app deps separately from Morph's own deps:

```bash
pip install -r apps/requirements.txt
```
