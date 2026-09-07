# Morph: Faulty Demo Apps

> The deliberately faulty apps Morph reproduces failures in: what they are, the contract they follow, how each one is driven, and the measured numbers.

This document covers the demo failure corpus referenced in [PRD §13](./Morph_PRD.md) and [Design Spec §24](./Morph_Design_Spec.md). Read it before touching anything under `apps/`. The per-app READMEs carry the details; this is the map.

---

## Contents

1. [What these apps are](#1-what-these-apps-are)
2. [The interface contract](#2-the-interface-contract)
3. [Design rules every app must follow](#3-design-rules-every-app-must-follow)
4. [Repo layout](#4-repo-layout)
5. [The six apps](#5-the-six-apps)
6. [How a condition reaches an app](#6-how-a-condition-reaches-an-app)
7. [Verification protocol and acceptance](#7-verification-protocol-and-acceptance)
8. [Real bugs from GitHub](#8-real-bugs-from-github)
9. [Pitfalls](#9-pitfalls)

---

## 1. What these apps are

They are **controlled failure fixtures**, not randomly buggy programs. Each app is the smallest program where **one environment knob moves the failure rate from ~0 % to ~100 %** (or from ~0 % to a clear band, for the race), reliably, on demand.

Each one is engineered with:

- a known **trigger** (which condition causes it),
- a known **threshold** (the value at which it flips),
- a **clean baseline** (near-zero failures when the condition is absent),
- a **one-line fix** (so the fix, replay, PASS step of the demo is obvious on screen).

If an app fails unpredictably at baseline it is useless: the engine's baseline-vs-treatment comparison ([PRD §15](./Morph_PRD.md)) has nothing to measure against, and the live demo becomes a coin flip.

---

## 2. The interface contract

Every demo app exposes the **same** CLI so the Morph runtime never needs per-app special-casing.

```
python -m apps.<name> run             # run once, human-readable, exit 0 / 1 / 2
python -m apps.<name> test            # same, machine mode: last stdout line is a JSON object
python -m apps.<name> run --fixed     # the FIXED variant (flags accepted in any order)
```

`test` JSON line (one line, the last line of stdout):

```json
{"result": "pass|fail", "signal": "TimeoutException", "duration_ms": 253, "detail": "deadline 250ms exceeded"}
```

Rules:

- **Exit code is the source of truth.** `0` passed, `1` the engineered failure occurred, `2` an *invalid trial*: the app could not attempt the test (missing locale, unknown timezone, a resource limit too low to even start). Morph's collector sets `RunResult.invalid` on exit 2 (and on 126/127 and launch failures); the engine retries an invalid trial and never counts it as a pass or a failure. Exit 2 must therefore be reserved for genuinely invalid trials. An unfamiliar ambient locale, say, is a real trial, not an invalid one.
- **Fail only through the app's own contract.** Under Morph's proxy, packet loss is delivered as *delay* (a retransmission stall), never as corrupted bytes, so a network fixture fails through its deadline. A protocol error is a setup error (exit 2), not a failure.
- **Single process.** The app starts its own server (background thread) and tears it down. Morph runs one command; it does not orchestrate a client and a server.
- **Fast.** A baseline `test` run completes in well under a second. The failing legs of the flagship take up to ~3.3 s (its deadline plus one read timeout); that is the ceiling.
- **Deterministic teardown.** Bind port 0, `shutdown()` in a `finally`, restore state. A leaked server on trial 7 poisons trials 8 to 100.
- **Clean stderr.** Morph parses stderr for the failure signal. Expected client disconnects must not print tracebacks.
- **No network egress.** Everything is localhost. The core demo runs offline ([PRD §42](./Morph_PRD.md)).

---

## 3. Design rules every app must follow

| Rule | Why |
|---|---|
| Baseline fail rate < 5 % | Otherwise the engine cannot distinguish "condition caused it" from "app is flaky" |
| Sharp threshold (flips inside a narrow band) | Gives probabilistic bisection ([how-it-works §6](./how-it-works.md)) a real edge to find |
| Distinct failure signal (specific exception + one-line detail) | Feeds the four-way classification ([PRD §18](./Morph_PRD.md)) |
| Ship the fix as a one-line diff behind `--fixed` | The demo shows the fix passing under the *same* environment |
| Tuning knobs are env vars at the top of the file | Re-tuning must not need a code change |
| A self-check per app (`test_app.py`), two tiers | Contract tier (seconds, blocking in CI) and `slow` statistical tier (advisory) |

---

## 4. Repo layout

```
apps/
  README.md                 # one table: trigger, baseline, under condition, classification
  requirements.txt          # deps for the demo apps ONLY (httpx); NOT Morph's deps
  conftest.py               # shared run_app() helper, binomial bounds, marker skips
  netshape.py               # MORPH_NET_* hand-off: fronts an app's server with Morph's proxy
  timeout/                  # Failure A   latency -> deadline
  pool_retry/               # Failure B   latency x loss interaction (flagship)
  race/                     # Failure C   CPU quota exposes an unlocked check-then-act
  locale_parse/             # Failure D   comma-decimal locale corrupts a number
  fd_limit/                 # Failure E   RLIMIT_NOFILE exhausts a leaky pool
  tz_dst/                   # Failure F   "24 h later" across a DST transition
    __init__.py
    __main__.py             # python -m apps.<name> run|test [--fixed]
    app.py                  # the fixture; knobs at the top
    test_app.py             # contract tier + @pytest.mark.slow statistical tier
    README.md               # trigger, threshold, measured rates, the fix
profiles/                   # one EnvironmentProfile per demo condition (flagship.json, ...)
```

`apps/requirements.txt` is **separate** from the root `requirements.txt`: "what Morph needs to run" and "what the things Morph tests need to run" stay distinct. Morph runs an app in its own process; it never imports it.

---

## 5. The six apps

Measured on macOS (Darwin 25.5, Python 3.12) through the same `MORPH_NET_*` / `LC_ALL` / `TZ` / `setrlimit` paths Morph's runtime uses. Rates are failures over trials.

| App | Trigger | Baseline | Under condition | `--fixed` under condition | Classification |
|---|---|---|---|---|---|
| A `timeout` | latency (RTT) | 0/20 | 20/20 at 120 ms; flips at ~42 ms RTT | 0/20 | environment-caused |
| B `pool_retry` | latency **and** loss | 0/20 | 19/20 at 120 ms / 18 %; each alone 0/20 | 0/20 | environment-caused, **interaction** |
| C `race` | CPU quota; root-free `MORPH_C_YIELD_EVERY` | 0/10, rate 0.000 | 10/10, rate 0.28 to 0.40 (N=2) | 0/10 | environment-**exposed** |
| D `locale_parse` | `LC_ALL`/`LANG` comma-decimal (de_DE) | 0/5 in a C.UTF-8 shell | 5/5 | 0/5 | environment-caused |
| E `fd_limit` | `process.fd_limit` (RLIMIT_NOFILE) | 0/10 | 10/10 at 64; flips between 96 and 112 | 0/10 | environment-caused |
| F `tz_dst` | `TZ` (America/Sao_Paulo) | 0/5 (UTC) | 5/5 | 0/5 | environment-caused |

### A. `timeout`: deadline under latency

A client with a 250 ms deadline calls a local server that takes ~200 ms. Baseline ~208 ms. Round-trip latency of 42 ms or more pushes the response past the deadline: measured 0/5 at 40 ms, 5/5 at 45 ms. Under loss alone it also fails (about 1 request in 3 at 18 %), because a 200 ms retransmission stall is far larger than the 45 ms of headroom; that is the correct behaviour of a tight deadline, not a fixture defect, and it is why `pool_retry`, not `timeout`, is the single-variable-clean fixture. Fix: `--fixed` raises the deadline to 1 s. [README](../apps/timeout/README.md).

### B. `pool_retry`: the interaction (flagship)

Sixteen requests through a two-slot connection pool, 0.5 s read timeout, five retries, one 2.8 s batch deadline; the server answers in 80 ms. The interaction is in how loss costs time on TCP: a stall is `max(200 ms, 3 x RTT)`.

- latency alone (120 ms RTT): 200 ms per request, eight waves, ~1.7 s, PASS
- loss alone (18 %): a stall is 200 ms; 80 + 200 fits inside the 500 ms read timeout, PASS
- both: the stall is 360 ms; 200 + 360 is past the read timeout, every loss burns a slot for 500 ms and the retry re-queues; eight waves cascade past 2.8 s, FAIL

`--fixed` sizes the pool to the batch, so no request queues behind a stalled one. Fix and operating point are in the [README](../apps/pool_retry/README.md); `profiles/flagship.json` and `morph demo` carry the operating point.

### C. `race`: environment-exposed

Eight threads meet at a barrier and run an unlocked check-then-act on a shared cache. A calm CPU hides it (rate 0.000). A cgroup CPU quota (Linux, root) freezes the process at budget exhaustion; when a freeze lands inside the window another thread races in. macOS and Windows have no cgroups, so the root-free knob `MORPH_C_YIELD_EVERY=N` inserts one `time.sleep(0)` inside the window on every Nth iteration: a preemption with the same direction of effect. N=2 gives a double-call rate of about 0.3, N=1 about 0.65. `profiles/race_yield.json` passes it through the profile's `env_vars`. Say in the demo that this is a stand-in, not a reproduced quota. The correct verdict is *exposed*, not *caused*: the bug is in the app. [README](../apps/race/README.md).

### D. `locale_parse`: silent data corruption

A config value `"1.5"` parsed with `locale.atof()`. Under C, POSIX, en_US or en_IN it reads 1.5. Under de_DE or fr_FR the period is the thousands separator, so it reads **15.0**, no exception. Baseline is the developer's own shell (no locale env); the condition is `LC_ALL=de_DE.UTF-8`, exactly what the adapters export for `locale.locale`. Exit 2 only when a *requested* registered locale is not installed or did not take effect (the false-evidence guard). [README](../apps/locale_parse/README.md).

### E. `fd_limit`: descriptor exhaustion, no root

A keep-alive pool that opens a new connection per request and never reaps. 48 requests hold ~110 descriptors. `profiles/fd_limit.json` requests `process.fd_limit = 64`; Morph applies it with `setrlimit(RLIMIT_NOFILE)` in the child, and the pool hits `EMFILE` at request 31. Flips between 96 (fails at request 47) and 112 (passes). Below 16 descriptors the app cannot start at all and exits 2. This is the non-network knob Morph can apply on a laptop with no privileges. [README](../apps/fd_limit/README.md).

### F. `tz_dst`: "same time tomorrow"

A scheduler computes the next nightly run as `last + 86400 s`. Under `TZ=America/Sao_Paulo` the anchor night (2018-11-03 23:30) has a midnight DST jump, the day is 23 h long, and the next run lands on 2018-11-05 00:30: a whole day skipped. Under `America/New_York` (fall-back that night) it fires an hour early. UTC and Asia/Kolkata pass. Exit 2 when `TZ` names a zone the host does not know (libc would silently use UTC and fake a PASS). [README](../apps/tz_dst/README.md).

---

## 6. How a condition reaches an app

Nothing here needs root. This is the path `morph run`, `morph experiment` and `morph threshold` use on a laptop.

| Condition | Profile field | What the adapter exports / applies | Which apps |
|---|---|---|---|
| latency, loss | `network.latency_ms` (an RTT), `network.packet_loss_percent` | `MORPH_NET_LATENCY_MS`, `MORPH_NET_PACKET_LOSS_PCT` (and `MORPH_SEED`); the app fronts its own server with Morph's proxy via `apps/netshape.py` | timeout, pool_retry |
| locale | `locale.locale` | `LC_ALL`, `LANG` | locale_parse |
| timezone | `locale.timezone` | `TZ` | tz_dst |
| descriptor limit | `process.fd_limit` | `setrlimit(RLIMIT_NOFILE)` before exec | fd_limit |
| CPU quota | `cpu.quota_percent` | cgroup `cpu.max` (Linux, root); elsewhere the `MORPH_CPU_QUOTA_PERCENT` hint only | race |
| anything | `env_vars` | exported verbatim | race (`MORPH_C_YIELD_EVERY`) |

With root, the Linux adapter shapes `lo` with `tc netem` and the macOS adapter uses dummynet through `pf`; the `MORPH_NET_*` variables are then absent and the in-app proxy is a no-op. Latency is an RTT in both paths: the proxy adds half per direction, and the native adapters halve the value for their per-direction delay.

Manual equivalents, for checking an app without Morph:

```bash
MORPH_NET_LATENCY_MS=120 python -m apps.timeout test
MORPH_NET_LATENCY_MS=120 MORPH_NET_PACKET_LOSS_PCT=18 python -m apps.pool_retry test
LC_ALL=de_DE.UTF-8 LANG=de_DE.UTF-8 python -m apps.locale_parse test
TZ=America/Sao_Paulo python -m apps.tz_dst test
MORPH_C_YIELD_EVERY=2 python -m apps.race test
python -c 'import resource,runpy,sys; resource.setrlimit(resource.RLIMIT_NOFILE,(64,64)); sys.argv=["x","test"]; runpy.run_module("apps.fd_limit", run_name="__main__")'

# Linux, root: the native path
sudo tc qdisc add dev lo root netem delay 60ms loss 18%     # 60 ms per direction = 120 ms RTT
sudo tc qdisc del dev lo root                               # ALWAYS remove between conditions
systemd-run --scope -p CPUQuota=10% python -m apps.race test
```

Locales must be generated (`locale -a`; on Debian `sudo sed -i 's/# de_DE.UTF-8/de_DE.UTF-8/' /etc/locale.gen && sudo locale-gen`); GitHub's `ubuntu-latest` ships only C and en_US, and the corpus tests skip the de_DE legs when it is missing. Timezones need `tzdata`.

---

## 7. Verification protocol and acceptance

Two tiers, both in `apps/*/test_app.py`:

```bash
pytest apps -m "not slow"     # contract tier: baseline passes, condition fails, exit codes, JSON line; ~10 s; blocking in CI
pytest apps -m slow           # statistical tier: the acceptance rates below over 10 to 20 trials; advisory in CI
```

The statistical tier asserts with **binomial-aware bounds** (`apps/conftest.py`): a healthy fixture is rejected at most 1 % of the time. "Baseline < 5 %" over 20 trials therefore allows up to 3 failures, and "combined > 80 %" requires at least 11 of 12. Never assert zero failures over eight trials of a stochastic fixture; at a true rate of 5 % that fails a third of the time.

| App | baseline fail rate | under-condition fail rate | `--fixed` under condition |
|---|---|---|---|
| A timeout | < 5 % | > 90 % | < 5 % |
| B pool_retry, combined | < 5 % | > 80 % | < 10 % |
| B pool_retry, single variable | not applicable | < 15 % | not applicable |
| C race (yield knob) | < 5 % | > 50 % of runs; double-call rate 0.2 to 0.8 | 0 % |
| D locale | 0 % | 100 % | 0 % |
| E fd_limit | < 5 % | 100 % | 0 % |
| F tz_dst | 0 % | 100 % | 0 % |

If the numbers go mushy: **tune the app, never tune Morph around a flaky app.**

Then prove it through Morph, which is the only verification that counts for the demo:

```bash
morph run -p profiles/flagship.json -c "python -m apps.pool_retry test"        # exit 1
morph run -c "python -m apps.pool_retry test"                                   # exit 0
morph demo                                                                      # the sequential 2x2, live
morph threshold -c "python -m apps.timeout test" --parameter network.latency_ms --low 0 --high 120
```

---

## 8. Real bugs from GitHub

The synthetic apps are the reliable backbone. `tz_dst` is already the pure-Python form of a documented real bug (moment-timezone #672, #728, #967; pytz #56). Two further capstones are worth adding **only after** the synthetic pipeline runs end to end; neither exists in the repo today.

### 8.1 Turkish locale `toLowerCase` (JVM)

Python's `str.lower()` is not locale-sensitive, so this cannot be reproduced in pure Python. A minimal Java reproduction (`"ID".toLowerCase()` yielding dotless `ıd` under `-Duser.language=tr`) cites Akka #15828, Gradle #1506, ONLYOFFICE DocumentServer #3402 and i18next #157. Env knob: `LANG=tr_TR.UTF-8` or the JVM flag. Fix: `toLowerCase(Locale.ROOT)`. Needs a JDK on the runner.

### 8.2 `requests` without a default timeout (maps to Failure A)

psf/requests #3070. `requests.get(url)` with no `timeout=` against a slow server hangs forever; wrap it in a watchdog to turn the hang into a measurable FAIL. Fix: `timeout=(3, 10)`.

### 8.3 Filesystem case sensitivity

`import Button from './components/button'` where the file is `Button.tsx`: passes on macOS, fails on Linux. Needs a JS toolchain and a case-sensitive image on macOS (`hdiutil create -fs "Case-sensitive APFS"`); Morph's profiler captures `filesystem.case_sensitive` but no adapter mounts an image yet.

---

## 9. Pitfalls

- **`tc netem` on `eth0` does nothing to `127.0.0.1`.** Shape `dev lo`. The netem delay is per direction: use half the RTT you mean.
- **Latency is an RTT everywhere.** The profile value, `MORPH_NET_LATENCY_MS`, and a threshold Morph reports are round-trip figures. Older notes that said "one-way, so the RTT is 2x" describe the old proxy and are wrong now.
- **Loss is delay, not corruption.** An app that "fails" under loss with a parse error is broken; make it fail through its deadline.
- **Exit 2 is discarded, not counted.** Use it only for a trial the app could not attempt. Using it for a legitimate failure hides evidence; using exit 1 for a setup error fabricates evidence.
- **The corpus strips the developer's environment.** `apps/conftest.py` removes `LC_*`, `LANG`, `TZ` and `MORPH_NET_*` before every run, so a German shell or a Sao Paulo laptop cannot turn a baseline into a treatment.
- **CPU core pinning (`taskset`) is not quota throttling (`cpu.max`).** Pinning can *reduce* the race. Use the quota; on macOS/Windows use the yield knob and say so.
- **Python `str.lower()` is not locale-sensitive.** Python locale bugs go through `locale.atof` / `strptime` / `strcoll`.
- **Leaked servers poison the batch.** Bind port 0; `shutdown()` and `server_close()` in a `finally`.
- **Threshold search assumes failure increases with the parameter.** `process.fd_limit` is the inverse (low values fail); search it with the roles of `--low` and `--high` in mind, or pass the negated quantity.
- **Don't build the demo around a real bug you haven't reproduced yet.** Synthetic apps first, real capstone second.
