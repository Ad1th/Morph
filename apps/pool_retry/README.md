# Failure B: latency AND packet loss interaction (FLAGSHIP)

**Trigger:** network latency **and** packet loss, *together*. Neither alone.
**Baseline:** batch ~550ms -> PASS.
**Classification:** environment-caused, **interaction**.
**Fix:** `POOL_MAX = N_REQUESTS` (no queueing) via `--fixed`.

## Why this is the flagship

Every other fixture flips on a single toggle. This one does not:

```
latency alone       PASS
packet loss alone   PASS
latency + loss      FAIL
```

That is the claim Morph exists to make ([PRD §13](../../docs/Morph_PRD.md),
[§17](../../docs/Morph_PRD.md)): a tool that only toggles one variable at a time
would test both conditions, see both pass, and conclude the environment is fine.
Only a controlled experiment across the *combination* finds this.

## Mechanism

`N_REQUESTS` concurrent requests share a `POOL_MAX`-slot connection pool, with
bounded retries and one overall wall-clock deadline. The server answers in ~80ms.

- **Latency alone** — every request costs 80ms + RTT. With `POOL_MAX` slots the
  batch runs in `ceil(N/POOL)` waves: slower, but inside the deadline.
- **Loss alone** — a dropped chunk means the response never arrives, so that
  request stalls until its read timeout fires and then retries. At low latency
  the retry is cheap and the other requests drain through the free slot.
- **Both** — the stalled request holds its pool slot for the *whole* read
  timeout, while every remaining request is now also slow. They queue behind a
  pool that is effectively half its size, and the queue cascades past the
  deadline.

The interaction is the cascade. Latency alone doesn't fill the queue; loss alone
doesn't slow the drain. Only together does the queue outgrow the budget.

## Run it

```bash
python -m apps.pool_retry run           # baseline: PASS
python -m apps.pool_retry test          # machine mode
python -m apps.pool_retry run --fixed   # pool sized to the batch

# under real injected conditions
MORPH_B_PROXY_LATENCY_MS=90 MORPH_B_PROXY_LOSS_PCT=12 python -m apps.pool_retry test
```

Exit codes: `0` pass, `1` engineered failure (deadline exceeded), `2` setup error.

## Conditions are real, not simulated

Latency and loss are injected by Morph's own user-space TCP proxy
(`morph/runtime/adapters/proxy.py`), started in front of the server when either
knob is set. The proxy genuinely delays and genuinely drops chunks, so:

- a dropped response really never arrives, and the client's read timeout fires
  on a real connection;
- **latency is applied per direction, so round-trip grows by ~2x the configured
  value** — `MORPH_B_PROXY_LATENCY_MS=90` is ~180ms RTT. Real `netem` on
  loopback behaves the same way, so this doubling is faithful rather than a
  quirk.

This replaced an earlier server-side simulation of the conditions. That mattered:
the simulated version could never satisfy the acceptance criteria (see below),
and its numbers would have needed recalibration against real shaping anyway.

The import of `morph` is lazy — the app runs standalone when no conditions are
set, so it keeps working as a plain fixture.

## Tuning knobs

| Var | Default | Meaning |
|---|---|---|
| `MORPH_B_N` | `12` | concurrent requests in the batch |
| `MORPH_B_POOL` | `2` | connection pool slots |
| `MORPH_B_DEADLINE` | `2.4` | whole-batch wall-clock budget (s) |
| `MORPH_B_REQ_TIMEOUT` | `0.5` | per-request read timeout (s) |
| `MORPH_B_RETRIES` | `4` | retries per request |
| `MORPH_B_SERVER_DELAY` | `0.08` | server response time (s) |
| `MORPH_B_PROXY_LATENCY_MS` | `0` | injected one-way latency (RTT is ~2x this) |
| `MORPH_B_PROXY_LOSS_PCT` | `0` | injected chunk-drop percentage |

## How the deadline was chosen

Measure the elapsed time of each leg **with the deadline disabled**
(`MORPH_B_DEADLINE=99`), then place the deadline in the gap. Doing it the other
way round — guessing a deadline and reading pass/fail rates — hides the overlap
and wastes cycles.

Measured, 10 runs per leg, sorted (ms):

| leg | min | max |
|---|---|---|
| baseline | 506 | 577 |
| loss alone (12%) | 883 | 1966 |
| `--fixed`, both | 758 | 2066 |
| latency alone (90ms) | 2034 | **2298** |
| **both** | **2466** | 3593 |

Everything that must pass tops out at **2298ms**; everything that must fail
starts at **2466ms**. The deadline sits at **2400ms**, inside that gap.

### If you re-tune

Two knobs matter, and they fail in opposite directions:

- **Loss rate** sets how often a drop happens *at all*. Too low and some runs of
  the combined leg see no drop, so "both" degenerates into "latency alone" and
  lands below the deadline. At 8% loss that happened in ~1 run in 8, which
  capped the combined failure rate at 87%. 12% fixed it.
- **Retries** protect the `--fixed` and `loss alone` legs. A request dies only if
  *every* attempt is dropped, with probability `loss^(retries+1)`, and no pool
  size can prevent that. At 2 retries this alone failed both legs.

Raise loss to strengthen the interaction; raise retries to stop that from
breaking the other legs.

## Verification status

| | status |
|---|---|
| Interaction; each variable alone passes; fix works | **verified** under real injected conditions |
| Same via OS-native shaping (`tc netem` / Clumsy / `dnctl`) | not yet measured |

The proxy is a genuine injection mechanism, not an approximation, and it is what
Morph uses on Windows and macOS where kernel shaping needs admin rights. Running
the same legs under `tc netem` on the Pi is still worth doing to confirm the
OS-native path agrees.
