# Morph: Faulty Demo Apps

> Everything needed to build the deliberately-faulty apps Morph reproduces failures in, plus how to pull real documented bugs from GitHub instead.

This document covers the demo failure corpus referenced in [PRD §13](./Morph_PRD.md) and [Design Spec §24](./Morph_Design_Spec.md). Read it before writing any demo app.

---

## Contents

1. [What these apps are](#1-what-these-apps-are)
2. [The interface contract](#2-the-interface-contract)
3. [Design rules every app must follow](#3-design-rules-every-app-must-follow)
4. [Repo layout](#4-repo-layout)
5. [The four synthetic apps](#5-the-four-synthetic-apps)
6. [Environment-knob reference (the actual commands)](#6-environment-knob-reference-the-actual-commands)
7. [Manual verification protocol](#7-manual-verification-protocol)
8. [Pulling real bugs from GitHub](#8-pulling-real-bugs-from-github)
9. [Build order and Review 1 target](#9-build-order-and-review-1-target)
10. [Pitfalls](#10-pitfalls)

---

## 1. What these apps are

They are **controlled failure fixtures**, not randomly buggy programs. Each app is the smallest possible program where **one environment knob moves the failure rate from ~0% to ~100%** (or ~0% → ~50% for the race app), reliably, on demand.

You are not writing "a buggy app." You are engineering a failure with:

- a known **trigger** (which condition causes it),
- a known **threshold** (the value at which it flips),
- a **clean baseline** (near-zero failures when the condition is absent),
- a **one-line fix** (so the fix → replay → PASS demo step is obvious on screen).

If an app fails unpredictably at baseline, it is useless: the experiment engine's baseline-vs-treatment comparison ([PRD §15](./Morph_PRD.md)) has nothing to measure against, and the live demo becomes a coin flip.

---

## 2. The interface contract

Every demo app, synthetic or real-derived, exposes the **same** CLI so the Morph runtime never needs per-app special-casing.

```
<app> run            # run the scenario once, human-readable output, exit 0 (ok) / 1 (the failure) / 2 (crash/setup error)
<app> test           # same as run but machine-mode: last stdout line is a JSON object, exit 0/1/2
<app> --fixed run    # run the FIXED variant (or a separate fixed/ entrypoint)
```

`test` JSON line (one line, last line of stdout):

```json
{"result": "pass|fail", "signal": "TimeoutException", "duration_ms": 383, "detail": "deadline 250ms exceeded"}
```

Rules:

- **Exit code is the source of truth.** `0` = passed, `1` = the engineered failure occurred, `2` = something else broke (port in use, missing locale, etc.). Morph treats `2` as "invalid trial," not a failure.
- **Single process.** The app starts its own server (background thread or subprocess) and tears it down. Morph runs one command; it does not orchestrate a client and a server.
- **Fast.** One `test` run completes in < 1–2 s. The experiment engine runs 100+ trials per condition; a 5 s app makes one condition sweep take 8+ minutes.
- **Deterministic teardown.** Always free the port, kill the child, restore any state. A leaked server on trial 7 poisons trials 8–100.
- **No network egress.** Everything is localhost / bundled. The core demo runs offline ([PRD §42](./Morph_PRD.md)).

---

## 3. Design rules every app must follow

| Rule | Why |
|---|---|
| Baseline fail rate < 5% | Otherwise the experiment engine can't distinguish "condition caused it" from "app is just flaky" |
| Sharp threshold (flips inside a narrow band, e.g. 140–160 ms) | Gives the engine's bisection ([PRD §16](./Morph_PRD.md)) a real edge to find |
| Distinct failure signal (specific exception + one-line detail) | Feeds the CAUSED / EXPOSED / INCONCLUSIVE classification ([PRD §18](./Morph_PRD.md)) |
| Ship the fix as a one-line diff | The demo shows the fix making it pass under the *same* environment |
| Parameterise the tuning knobs (deadline, pool size, loop count) via env vars or constants at the top of the file | You *will* need to re-tune during the hackathon |
| One runnable self-check per app (`assert`-based `demo()` or a `test_*.py`) | Confirms the app still fails the way you think it does after you touch it |

---

## 4. Repo layout

```
apps/
  requirements.txt          # deps for the demo apps ONLY (httpx, moment via node, etc.) — NOT Morph's deps
  README.md                 # one-line-per-app: trigger | threshold | baseline rate
  timeout/                  # Failure A
    __init__.py
    app.py                  # `python -m apps.timeout run|test`
    fixed.py                # or a --fixed flag in app.py
    README.md               # trigger condition, expected threshold, baseline fail rate, the fix
  pool_retry/               # Failure B (flagship)
  race/                     # Failure C
  locale_parse/             # Failure D
  real/                     # apps pulled from GitHub (section 8)
    turkish_locale/
    saopaulo_dst/
```

`apps/requirements.txt` is **separate** from the root `requirements.txt`. "What Morph needs to run" and "what the things Morph tests need to run" must stay distinct — it is also a point worth showing a judge (Morph runs an app in its own environment; it does not import it).

---

## 5. The four synthetic apps

### Failure A: timeout under network latency

**Mechanism.** A client with a tight timeout calls a server that takes ~200 ms. Add latency, the response arrives after the timeout, the client raises.

```python
# apps/timeout/app.py  (sketch)
import http.server, threading, time, sys, json, httpx

RESP_DELAY_S   = 0.20
CLIENT_TIMEOUT = float(os.getenv("MORPH_A_TIMEOUT", "0.25"))   # tuning knob; --fixed sets 1.0

class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        time.sleep(RESP_DELAY_S)
        self.send_response(200); self.end_headers(); self.wfile.write(b"ok")
    def log_message(self, *a): pass

def main(machine_mode):
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    t0 = time.monotonic()
    try:
        httpx.get(f"http://127.0.0.1:{port}/", timeout=CLIENT_TIMEOUT)
        result, signal, detail = "pass", None, ""
    except httpx.TimeoutException as e:
        result, signal, detail = "fail", "TimeoutException", f"deadline {CLIENT_TIMEOUT*1000:.0f}ms exceeded"
    finally:
        srv.shutdown()
    dur = (time.monotonic() - t0) * 1000
    if machine_mode:
        print(json.dumps({"result": result, "signal": signal, "duration_ms": round(dur), "detail": detail}))
    sys.exit(0 if result == "pass" else 1)
```

| | value |
|---|---|
| Env knob Morph turns | network latency on `lo` |
| Baseline (0 ms added) | ~200 ms < 250 ms → PASS, ~100/100 |
| Fails when | added latency > ~50 ms |
| Fix (one line) | `CLIENT_TIMEOUT = 1.0` |
| Classification | **environment-caused** |

**Loopback gotcha:** the server is on `127.0.0.1`, so `tc netem` on `eth0`/`wlan0` does nothing. Shape the **loopback** interface (`dev lo` on Linux; dummynet on `lo` on macOS; Clumsy filtering localhost on Windows). See section 6. Fallback: run the server on the Pi and the client on the Mac, shaping the real NIC.

Build this first. It is the simplest and it exercises the whole pipeline.

---

### Failure D: locale-dependent parsing

**Mechanism (Python-appropriate).** `str.lower()` / `str.upper()` in Python 3 are **not** locale-sensitive (they use Unicode default casing), so the classic "Turkish i" bug **cannot** be reproduced in pure Python — reserve that for the real-app pull (section 8, it's a JVM bug). For a Python synthetic app use one of:

1. **Decimal comma via `locale.atof`:**

```python
import locale, sys, json, os
locale.setlocale(locale.LC_ALL, "")          # picks up LANG / LC_NUMERIC from the environment Morph sets
raw = "1,5"                                   # config value: one and a half, European style
val = locale.atof(raw)                        # de_DE -> 1.5 ; en_US -> ValueError or 1.0
ok = abs(val - 1.5) < 1e-6
```

2. **Localised month abbreviation:**

```python
import time
time.strptime("Mär 2026", "%b %Y")           # de_DE.UTF-8 -> ok ; en_US.UTF-8 -> ValueError
```

| | value |
|---|---|
| Env knob Morph turns | `LANG` / `LC_ALL` / `LC_NUMERIC` |
| Baseline | depends which locale you call "normal" — pick `en_US.UTF-8` as baseline PASS for variant 2, `de_DE.UTF-8` for variant 1 |
| Fails when | the other locale is set |
| Fix (one line) | parse with an explicit format/locale: `locale.atof` → `float(raw.replace(",", "."))`, or `strptime(..., locale="de_DE")` equivalent |
| Classification | **environment-caused** |

Fully deterministic (no timing, no randomness). Build this second. **The target locale must be installed** — see section 6 (the Pi minimal image ships almost none).

---

### Failure C: race condition exposed by CPU throttling

**Mechanism.** Two+ threads do an unlocked check-then-act. The race window is tiny under a normal CPU budget and rarely loses. Under a **cgroup CPU quota** (`cpu.max`), when the budget for the period is exhausted the whole process is frozen until the next period — if that freeze lands between one thread's *check* and its *act*, another thread races in. Throttling turns a 1-in-1000 race into a 1-in-2.

```python
# apps/race/app.py  (sketch)
import threading, time, sys, json, os

ITERS   = int(os.getenv("MORPH_C_ITERS", "2000"))
THREADS = int(os.getenv("MORPH_C_THREADS", "8"))
USE_LOCK = "--fixed" in sys.argv
_lock = threading.Lock()

def run_once():
    cache, calls = {}, [0]
    def get():
        if USE_LOCK: _lock.acquire()
        try:
            if "k" not in cache:              # check
                time.sleep(0)                 # yield: widen the window deterministically
                calls[0] += 1                 # act
                cache["k"] = calls[0]
        finally:
            if USE_LOCK: _lock.release()
    ts = [threading.Thread(target=get) for _ in range(THREADS)]
    [t.start() for t in ts]; [t.join() for t in ts]
    return calls[0]                           # expected: exactly 1

double = sum(1 for _ in range(ITERS) if run_once() != 1)
rate = double / ITERS
result = "fail" if rate > 0.05 else "pass"
print(json.dumps({"result": result, "signal": "RaceDetected", "detail": f"{double}/{ITERS} iters double-called", "rate": rate}))
sys.exit(0 if result == "pass" else 1)
```

| | value |
|---|---|
| Env knob Morph turns | **CPU quota** via cgroup `cpu.max` (NOT core pinning — see pitfalls) |
| Baseline (full CPU) | rate ~0.5–2% → PASS |
| Fails when | quota throttled to ≤ ~20% of one CPU → rate jumps to 30–60% |
| Fix (one line) | `USE_LOCK = True` (wrap the check-then-act in `_lock`) |
| Classification | **environment-exposed** — the bug is in the app; CPU throttling only makes it visible. This is the app that demonstrates the CAUSED-vs-EXPOSED distinction ([PRD §18](./Morph_PRD.md)), so it earns its build time |

macOS has no cgroups — CPU-quota reproduction routes to the Pi or a Linux VM. State this openly in the demo; it matches the PRD's limitations framing.

Build this third. Expect ~30 min tuning `ITERS` / `THREADS` / the `time.sleep(0)` yield to land baseline < 5% and throttled > 30%.

---

### Failure B: latency AND packet loss interaction (flagship)

**Mechanism.** Fails **only on the combination**. A client fires N concurrent requests through a small connection pool, with bounded retries and a total wall-clock deadline. Server responds in ~80 ms.

- **Latency alone (180 ms):** each request ~260 ms, 2 pool waves ≈ 520 ms, under the 2 s deadline, no retries → PASS.
- **Loss alone (2%):** a rare drop forces a retry, but at low latency the retry is cheap → PASS.
- **Both:** a dropped packet forces a retry; each attempt now costs 180 ms+ RTT; the stalled request holds its pool slot until its per-request timeout fires; the other requests queue behind 2 busy slots → cascade past the 2 s deadline → FAIL.

```python
# apps/pool_retry/app.py  (tuning knobs at top)
DEADLINE_S       = float(os.getenv("MORPH_B_DEADLINE", "2.0"))
POOL_MAX         = int(os.getenv("MORPH_B_POOL", "2"))     # --fixed sets this to N_REQUESTS
PER_REQ_TIMEOUT  = float(os.getenv("MORPH_B_REQ_TIMEOUT", "0.5"))
RETRIES          = int(os.getenv("MORPH_B_RETRIES", "2"))
N_REQUESTS       = int(os.getenv("MORPH_B_N", "6"))
SERVER_DELAY_S   = 0.08
```

Client: `httpx.Client(limits=httpx.Limits(max_connections=POOL_MAX), timeout=PER_REQ_TIMEOUT)`, fire `N_REQUESTS` via a thread pool, each with a manual retry loop, all wrapped in a single `DEADLINE_S` budget. `result = "fail"` if the whole batch doesn't finish inside `DEADLINE_S`.

| | value |
|---|---|
| Env knobs Morph turns | latency **and** packet loss on `lo` |
| Baseline | batch ≈ 240 ms → PASS |
| Latency alone / loss alone | PASS (needs headroom — tune `DEADLINE_S`) |
| Both | > 90% FAIL after tuning |
| Fix (one line) | `POOL_MAX = N_REQUESTS` (no queueing) — or give retries a fresh connection with an independent budget |
| Classification | **environment-caused, interaction** |

This is the hard one. Budget 45–60 min of tuning; target ~5% baseline fail, single-variable cases < 15% fail, combined > 90% fail. It is built **last** not because it is low priority — it's the flagship — but because it needs the other three working first as a fallback if the tuning runs long.

---

## 6. Environment-knob reference (the actual commands)

Run these manually to verify each app *before* wiring it into Morph. All need root / sudo / admin.

### Network: latency, packet loss, bandwidth

**Linux (incl. Raspberry Pi)** — `tc` + `netem`:

```bash
# apply to loopback for single-process demo apps
sudo tc qdisc add dev lo root netem delay 180ms loss 2% rate 10mbit
# inspect
tc qdisc show dev lo
# remove (ALWAYS remove between conditions)
sudo tc qdisc del dev lo root

# for cross-machine demos, shape the real interface instead
sudo tc qdisc add dev eth0 root netem delay 180ms loss 2%
```

Needs `CAP_NET_ADMIN` (root). `netem` on `eth0` does **nothing** to `127.0.0.1` traffic — use `dev lo` or go cross-machine.

**macOS** — `dnctl` + `pfctl` (dummynet):

```bash
sudo dnctl pipe 1 config delay 180 plr 0.02 bw 10Mbit/s
echo 'dummynet-anchor "morph"' | sudo pfctl -f -
echo 'dummynet in  quick on lo0 all pipe 1
dummynet out quick on lo0 all pipe 1' | sudo pfctl -a morph -f -
sudo pfctl -e
# teardown
sudo pfctl -a morph -F all ; sudo dnctl -q flush ; sudo pfctl -d
```

Alternative: Network Link Conditioner (GUI, from Xcode Additional Tools) — not scriptable, fine for a manual fallback only.

**Windows** — [clumsy](https://jagt.github.io/clumsy/):

```
clumsy.exe --filter "outbound and loopback" --lag on --lag-time 180 --drop on --drop-chance 2.0
```

### CPU quota

**Linux cgroup v2** (preferred — real container semantics):

```bash
sudo mkdir /sys/fs/cgroup/morph
echo "10000 100000" | sudo tee /sys/fs/cgroup/morph/cpu.max     # 10ms per 100ms = 10% of one CPU
echo $PID           | sudo tee /sys/fs/cgroup/morph/cgroup.procs
# teardown: move pid out, then  sudo rmdir /sys/fs/cgroup/morph
```

Or one-liner per run:

```bash
systemd-run --scope -p CPUQuota=10% python -m apps.race test
```

Core pinning (different mechanism, less reliable for exposing races — see pitfalls):

```bash
taskset -c 0 python -m apps.race test
```

**macOS**: no cgroups. Use `cpulimit` (`brew install cpulimit`, userspace, approximate) or route CPU-constraint demos to the Pi / a Linux VM.

**Windows**: Job Objects (`JOBOBJECT_CPU_RATE_CONTROL_INFORMATION`) via a small helper, or `(Get-Process -Id $PID).ProcessorAffinity = 1` for core pinning.

### Memory limit

```bash
# Linux
systemd-run --scope -p MemoryMax=512M python -m apps.something test
# or cgroup:  echo 536870912 > /sys/fs/cgroup/morph/memory.max
# or:         ulimit -v 524288   (KB, address space, blunt)
```

macOS/Windows: `ulimit -v` partial on macOS; Job Object memory limit on Windows; otherwise route to the Pi.

### Locale

```bash
# Linux/macOS: set per-run
LANG=de_DE.UTF-8 LC_ALL=de_DE.UTF-8 python -m apps.locale_parse test

# the locale must be GENERATED first. Check:
locale -a
# Debian/Ubuntu/Raspberry Pi OS:
sudo sed -i 's/# de_DE.UTF-8/de_DE.UTF-8/' /etc/locale.gen && sudo locale-gen
# Alpine / minimal: install  musl-locales  or switch base image
```

**The Raspberry Pi Lite image ships almost no locales.** Generate `de_DE.UTF-8`, `en_US.UTF-8`, `tr_TR.UTF-8`, `en_IN` during setup and cache them.

**Windows**: OS locale needs a reboot (`Set-WinSystemLocale`) — impractical per run. On Windows, pass the locale to the app as an explicit `--locale de_DE` arg that calls `locale.setlocale(locale.LC_ALL, "de_DE")` instead of relying on the environment.

### Timezone

```bash
TZ=America/Sao_Paulo python -m apps.saopaulo_dst test    # Linux/macOS
```

Needs `tzdata` (`sudo apt install tzdata` on the Pi). On Windows, `TZ` is honoured inconsistently across runtimes — pass as an arg.

### Filesystem case sensitivity

Cannot be toggled on a live filesystem. Options:

```bash
# macOS: a case-sensitive APFS image
hdiutil create -size 200m -fs "Case-sensitive APFS" -volname morphcs /tmp/morphcs.dmg
hdiutil attach /tmp/morphcs.dmg
```

Or just use the natural split: macOS (case-insensitive) = PASS, Linux/Pi (case-sensitive) = FAIL.

---

## 7. Manual verification protocol

For every app, before it touches Morph:

```bash
# 1. baseline
for i in $(seq 1 50); do python -m apps.timeout test >/dev/null; echo $?; done | sort | uniq -c
#   expect ~50x "0"

# 2. apply the condition
sudo tc qdisc add dev lo root netem delay 180ms
for i in $(seq 1 50); do python -m apps.timeout test >/dev/null; echo $?; done | sort | uniq -c
#   expect ~50x "1"

# 3. remove the condition
sudo tc qdisc del dev lo root
```

**Acceptance:**

| App | baseline fail rate | under-condition fail rate |
|---|---|---|
| A timeout | < 5% | > 90% |
| B pool/retry (combined) | < 5% | > 90% |
| B pool/retry (single variable) | — | < 15% |
| C race | < 5% | 30–60% |
| D locale | 0% | 100% |

If the numbers are mushy: **tune the app, never tune Morph around a flaky app.** A demo app that only sometimes fails under its condition will make Morph look broken.

---

## 8. Pulling real bugs from GitHub

Keep the four synthetic apps as the reliable backbone. Add **one** real documented bug as a "this works on real software, not our toy" capstone — do it only after the synthetic pipeline runs end to end.

### 8.1 Turkish locale `toLowerCase` (recommended real capstone)

- **Real evidence:** [Akka #15828](https://github.com/akka/akka/issues/15828), [Gradle #1506](https://github.com/gradle/gradle/issues/1506), [ONLYOFFICE DocumentServer #3402](https://github.com/ONLYOFFICE/DocumentServer/issues/3402), [i18next #157](https://github.com/i18next/i18next-node/issues/157), plus JNativeHook, Applied Energistics.
- **Why not pure Python:** Python's `str.lower()` is not locale-sensitive. This is a JVM/.NET bug. Use a minimal faithful Java reproduction and cite the real issues as proof the pattern is widespread.
- **Minimal repro** (`apps/real/turkish_locale/App.java`):

```java
public class App {
    static java.util.Map<String,String> config = java.util.Map.of("id", "resolved");
    public static void main(String[] a) {
        String key = "ID";
        String looked = config.get(key.toLowerCase());          // BUG: unqualified toLowerCase
        // FIX: key.toLowerCase(java.util.Locale.ROOT)
        if (looked == null) { System.out.println("{\"result\":\"fail\",\"signal\":\"NullLookup\"}"); System.exit(1); }
        System.out.println("{\"result\":\"pass\"}"); System.exit(0);
    }
}
```

- **Run:** `java -Duser.language=tr -Duser.country=TR App` → `"ID".toLowerCase()` → `"ıd"` (dotless i) → lookup misses → exit 1. `java -Duser.language=en App` → pass.
- **Env knob Morph turns:** `LANG=tr_TR.UTF-8` (or the JVM `-Duser.language=tr`).
- **Fix:** `key.toLowerCase(Locale.ROOT)` — one-line diff.
- Needs a JDK on the runner; cache it on the 1 TB drive.

### 8.2 America/Sao_Paulo DST-at-midnight (optional second real bug)

- **Real evidence:** [moment-timezone #672](https://github.com/moment/moment-timezone/issues/672), [#728](https://github.com/moment/moment-timezone/issues/728), [#967](https://github.com/moment/moment-timezone/issues/967); [pytz #56](https://github.com/stub42/pytz/issues/56).
- **JS repro:** pin the buggy versions —

```bash
cd apps/real/saopaulo_dst && npm install moment@2.20.1 moment-timezone@0.5.14
```

```js
const moment = require('moment-timezone');
const got = moment.tz('2018-11-04 00:00', 'America/Sao_Paulo').add(1, 'day').format();
const want = '2018-11-05T00:00:00-02:00';
process.stdout.write(JSON.stringify({result: got === want ? 'pass' : 'fail', got, want}) + '\n');
process.exit(got === want ? 0 : 1);
```

- **Env knob Morph turns:** `TZ=America/Sao_Paulo` (plus the fixed input date — the bug lives in the library's tz data + the date landing on the DST switch).
- **Fix:** upgrade `moment-timezone` to a version with corrected tz data.
- Needs Node + the pinned modules cached offline.

### 8.3 `requests` has no default timeout (optional, maps to Failure A)

- **Real evidence:** [psf/requests #3070](https://github.com/psf/requests/issues/3070) (open for years), [algorithmia-python #41](https://github.com/algorithmiaio/algorithmia-python/issues/41).
- **Repro:** `requests.get(url)` with **no** `timeout=`, against a local server that sleeps 30 s. Wrap the call in a 5 s watchdog (`threading.Timer` or `signal.alarm`) to convert "hangs forever" into a measurable FAIL.
- **Env knob:** the server delay is the condition; or keep the server fast and add `tc` latency plus a short watchdog.
- **Fix:** `requests.get(url, timeout=(3, 10))`.

### 8.4 GOMAXPROCS / cgroup CPU quota (advanced, only if you have a Go demo app)

- **Real evidence:** [golang/go #73193](https://github.com/golang/go/issues/73193), [uber-go/automaxprocs](https://github.com/uber-go/automaxprocs).
- This is **performance degradation, not binary pass/fail** — a CPU-bound Go server under `CPUQuota=200%` with default `GOMAXPROCS` throttles; P99 latency spikes, RPS drops. To make it a pass/fail you must add a latency SLO the degraded case violates.
- **Fix:** `import _ "go.uber.org/automaxprocs"`.
- Python analogue (no Go needed): `ThreadPoolExecutor(max_workers=os.cpu_count())` on a box reporting 16 cores but constrained to 1 via `cpu.max` → oversubscription → throughput collapse; fix = size the pool to the cgroup quota, not `os.cpu_count()`.
- Mark optional. It's the weakest demo of the set because the failure isn't crisp.

### 8.5 Filesystem case sensitivity (easy, needs a JS toolchain)

- **Real evidence:** the canonical "passes on my Mac, fails in CI" — thousands of issues across the ecosystem.
- **Repro:** a tiny project with `import Button from './components/button'` where the file is `Button.tsx`. `tsc` / `vite build` passes on macOS (case-insensitive FS), fails on Linux/Pi (`Cannot find module './components/button'`).
- **Env knob Morph turns:** the filesystem-behaviour dimension — run on a case-sensitive FS (Linux/Pi, or a case-sensitive image on macOS from section 6).
- **Fix:** correct the import casing.

---

## 9. Build order and Review 1 target

| Order | App | Why this slot |
|---|---|---|
| 0 | Scaffold `apps/`, the interface contract, `apps/requirements.txt` | Unblocks everyone |
| 1 | **A — timeout** | Simplest; exercises the whole capture → reproduce → experiment → isolate pipeline |
| 2 | **D — locale** | Fully deterministic, fastest to make bulletproof |
| 3 | **C — race / CPU quota** | The environment-*exposed* demo; needed for the CAUSED-vs-EXPOSED story |
| 4 | **B — latency × loss** | Flagship, tuning-heavy; needs 1–3 done first as a fallback |
| 5 (post-pipeline) | **8.1 Turkish locale** real repro | Credibility capstone |

[PRD §13](./Morph_PRD.md) says A + B are the Review 1 requirement. In practice **A + D + C is a safer Review 1** than a half-tuned B alone — if B's interaction tuning isn't landing by the Phase 4 checkpoint, demo A/D/C and bring B to Review 2.

---

## 10. Pitfalls

- **`tc netem` on `eth0` does nothing to `127.0.0.1`.** Shape `dev lo`, or run client and server on different machines.
- **The Raspberry Pi Lite image has no locales and no tzdata.** Generate `en_US`, `de_DE`, `tr_TR`, `en_IN` and install `tzdata` during setup; cache them on the 1 TB drive.
- **Python `str.lower()` / `str.upper()` are not locale-sensitive.** Don't try to reproduce the Turkish-i bug in pure Python — that's the JVM real-app pull (8.1). Python locale bugs go through `locale.atof` / `strptime` / `strcoll`.
- **CPU core pinning (`taskset`) ≠ CPU quota throttling (`cpu.max`).** Pinning to one core can actually *reduce* certain races (less true parallelism). Quota throttling — freezing the whole process at budget exhaustion — is the reliable race *exposer*. Use `cpu.max` for Failure C.
- **HTTP keep-alive / connection reuse can hide the condition** while you tune B. Force a fresh connection per attempt, or disable keep-alive, until the numbers are stable, then decide what the "fixed" version restores.
- **Leaked servers poison the trial batch.** Bind to port `0` (OS picks a free port), always `srv.shutdown()` in a `finally`.
- **macOS has no cgroups.** CPU- and memory-constraint reproduction routes to the Pi or a Linux VM — say so in the demo; it matches the PRD's honest-limitations framing, it doesn't weaken it.
- **Running as non-root can't touch `tc` / cgroups.** Document the sudo requirement; consider `systemd-run --user` where available, or pre-authorise the specific commands via sudoers on the demo machines.
- **Don't build the demo around a real bug you haven't reproduced yet.** Synthetic apps first, real capstone second.
