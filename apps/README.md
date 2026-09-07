# Morph Demo Apps

Controlled failure fixtures used to demonstrate Morph's capture, reproduce,
experiment, isolate, fix, replay loop. See [docs/faultyapps.md](../docs/faultyapps.md)
for the design rules, the condition hand-off and the verification protocol, and
[docs/how-it-works.md](../docs/how-it-works.md) for what the engine does with
the trials.

Every app exposes the same CLI contract:

```
python -m apps.<name> run             # human-readable; exit 0 (pass) / 1 (engineered failure) / 2 (invalid trial)
python -m apps.<name> test            # machine mode: last stdout line is a JSON result object
python -m apps.<name> run --fixed     # the fixed variant (flags in any order)
```

`test` JSON line: `{"result": "pass|fail", "signal": "...", "duration_ms": N, "detail": "..."}`

Exit 2 is reserved for a trial the app could not attempt (locale not installed,
unknown timezone, a descriptor limit too low to start). Morph marks such a
`RunResult` `invalid`, retries it, and never counts it as a pass or a failure.

## Apps

Measured on macOS (Darwin 25.5, Python 3.12) through the paths Morph's runtime
uses (`MORPH_NET_*` hand-off to Morph's own proxy, `LC_ALL`/`LANG`, `TZ`,
`setrlimit`). Failures / trials.

| App | Trigger (profile field) | Baseline | Under condition | `--fixed` under condition | Classification |
|---|---|---|---|---|---|
| [timeout](timeout/) | latency, an RTT (`network.latency_ms`) | 0/20 | 20/20 at 120 ms; flips at ~42 ms | 0/20 | environment-caused |
| [pool_retry](pool_retry/) (flagship) | latency **and** loss | 0/20 | **19/20** at 120 ms / 18 %; latency alone 0/20, loss alone 0/20 | 0/20 | environment-caused, **interaction** |
| [race](race/) | CPU quota (`cpu.quota_percent`, Linux root) or `env_vars.MORPH_C_YIELD_EVERY` | 0/10, rate 0.000 | 10/10, rate 0.28 to 0.40 | 0/10 | environment-**exposed** |
| [locale_parse](locale_parse/) | comma-decimal locale (`locale.locale` = de_DE) | 0/5 | 5/5 | 0/5 | environment-caused |
| [fd_limit](fd_limit/) | descriptor limit (`process.fd_limit` = 64) | 0/10 | 10/10; flips between 96 and 112 | 0/10 | environment-caused |
| [tz_dst](tz_dst/) | timezone (`locale.timezone` = America/Sao_Paulo) | 0/5 | 5/5 | 0/5 | environment-caused |

`profiles/` holds one `EnvironmentProfile` per condition (`flagship.json`,
`high_latency.json`, `locale_de.json`, `fd_limit.json`, `tz_dst.json`,
`race_yield.json`). Each was generated on this Mac; the `os`/`cpu`/`memory`
sections are captured host values, and only the demo condition is `requested`.
Regenerate on another host with `morph define` or the snippet in
`profiles/README.md`.

```bash
morph run -p profiles/flagship.json -c "python -m apps.pool_retry test"   # exit 1
morph run -c "python -m apps.pool_retry test"                              # exit 0
morph demo                                                                 # the sequential 2x2, live
```

### The flagship: Failure B, the interaction fixture

Verified end to end through `morph experiment` in sequential mode (paired
trials, anytime-valid e-values) and standalone through the `MORPH_NET_*`
hand-off, 20 trials per leg. Operating point **120 ms RTT / 18 % loss**,
`N=16` requests through a 2-slot pool, 0.5 s read timeout, 5 retries, 2.8 s
deadline:

| leg | target | measured (20 trials) | duration min / median / max |
|---|---|---|---|
| baseline | < 5 % | 0/20 | 694 / 706 / 720 ms |
| latency alone (120 ms) | < 15 % | 0/20 | 1681 / 1701 / 1711 ms |
| loss alone (18 %) | < 15 % | 0/20 | 927 / 1869 / 2508 ms |
| latency + loss | > 80 % | **19/20** | 2206 / 3731 / 4509 ms |
| `--fixed` under both | < 10 % | 0/20 | 716 / 1229 / 2237 ms |

Why the pair and not either alone: a lost packet costs a retransmission stall
of `max(200 ms, 3 x RTT)`. At 0 ms RTT that is 200 ms, which fits inside the
500 ms read timeout; at 120 ms RTT it is 360 ms, and 200 + 360 does not. Every
loss then burns a pool slot for a full read timeout, and sixteen requests
queued behind two slots cascade past the deadline. `morph demo` and
`morph define -t high-latency` emit this operating point.

Through the engine (`morph experiment -p profiles/flagship.json -c "python -m
apps.pool_retry test"`, sequential mode, 12 rounds max): baseline 0/12,
`latency_only` 0/12, `loss_only` 0/12, `full_treatment` 9/9 and stopped early
at E = 102 (anytime p = 0.0098), verdict `environment_caused`. The same with
`--fixed`: every leg 0/12, verdict `no_effect`.

## How the condition reaches the app

Apps that host their own localhost server (`timeout`, `pool_retry`) read the
generic `MORPH_NET_LATENCY_MS` / `MORPH_NET_PACKET_LOSS_PCT` (plus optional
`MORPH_NET_BANDWIDTH_KBPS`, `MORPH_SEED`) the runtime exports on its
unprivileged proxy path and put Morph's own TCP proxy in front of their server
(`apps/netshape.py`). `MORPH_B_PROXY_*` are per-app overrides that win when
*set* (a value of `0` counts as set). When Morph shapes the interface natively
(root + `tc netem` / dummynet) those variables are absent and the in-app proxy
is a no-op.

**Latency is a round-trip time** everywhere: in the profile, in
`MORPH_NET_LATENCY_MS`, in the proxy (which adds half per direction), in the
native adapters (which halve it for their per-direction delay), and in any
threshold Morph reports. **Loss is delay, not corruption**: a lost chunk
arrives late after the stall above, so every network fixture fails through its
deadline and never through a parse error.

`locale_parse` reads `LC_ALL`/`LANG`, `tz_dst` reads `TZ`, `fd_limit` sees the
`RLIMIT_NOFILE` Morph sets before exec, and `race` reads `MORPH_C_YIELD_EVERY`
from the profile's `env_vars` (or, on Linux with root, is throttled by a real
cgroup quota and reads nothing).

## Tests

```bash
pytest apps -m "not slow"     # contract tier: ~10 s, blocking in CI
pytest apps -m slow           # statistical tier: binomial-aware rates, advisory in CI
```

Markers (`slow`, `needs_linux`, `needs_root`) are registered in
`pyproject.toml` with `--strict-markers`; `apps/conftest.py` skips the
platform-bound ones and provides `run_app()` and the binomial bounds. The
de_DE legs skip on hosts without that locale (GitHub's ubuntu image).

## Not done yet

- Cross-check the proxy path against `tc netem` on the Pi for `timeout` and
  `pool_retry`; the operating point above is proxy-measured.
- Measure `race` under a real cgroup quota on the Pi (`needs_linux` test).
- `morph threshold` assumes failure increases with the parameter;
  `process.fd_limit` is the inverse.

Install demo-app deps separately from Morph's own deps:

```bash
pip install -r apps/requirements.txt
```
