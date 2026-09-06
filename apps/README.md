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

| App | Trigger | Baseline fail rate | Under condition | Classification |
|---|---|---|---|---|
| [timeout](timeout/) | network latency on `lo` | < 5% | > 90% | environment-caused |
| [locale_parse](locale_parse/) | `LANG` / `LC_NUMERIC` | 0% | 100% | environment-caused |
| [race](race/) | CPU quota (cgroup `cpu.max`) | < 5% | 30-60% | environment-exposed |
| [pool_retry](pool_retry/) (flagship) | latency **+** packet loss combined | < 5% | > 90% (each alone < 15%) | environment-caused, interaction |
| [real/turkish_locale](real/turkish_locale/) | `LANG=tr_TR.UTF-8` (JVM) | 0% | 100% | environment-caused (real-world capstone) |

Install demo-app deps separately from Morph's own deps:

```bash
pip install -r apps/requirements.txt
```
