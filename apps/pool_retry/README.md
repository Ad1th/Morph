# Failure B: latency AND packet loss interaction (FLAGSHIP)

**Trigger:** network latency **and** packet loss, together. Neither alone.
**Operating point:** 120 ms RTT / 18 % loss (`profiles/flagship.json`, `morph demo`, `morph define -t high-latency`).
**Baseline:** batch ~700 ms against a 2.8 s deadline, 0/20 fail.
**Under condition:** 19/20 fail; latency alone 0/20, loss alone 0/20.
**Classification:** environment-caused, **interaction**.
**Fix:** `POOL_MAX = N_REQUESTS` (no queueing) via `--fixed`; 0/20 fail under the combination.

## Why this is the flagship

Every other fixture flips on a single toggle. This one does not:

```
latency alone       PASS
packet loss alone   PASS
latency + loss      FAIL
```

That is the claim Morph exists to make ([PRD §13](../../docs/Morph_PRD.md),
[§17](../../docs/Morph_PRD.md)): a tool that toggles one variable at a time
would test both conditions, see both pass, and conclude the environment is
fine. Only the 2x2 finds this, and `morph experiment` runs it as paired,
sequential trials with an anytime-valid e-value per candidate
([how-it-works §4 and §5](../../docs/how-it-works.md)).

## Mechanism

`N_REQUESTS` concurrent requests share a `POOL_MAX`-slot connection pool, with
a per-request read timeout, bounded retries and one overall wall-clock
deadline. The server answers in ~80 ms.

The interaction lives in how a lost packet costs *time* on a real TCP path. A
loss is not a missing byte, it is a retransmission stall of about
`max(200 ms, 3 x RTT)`: Linux's minimum RTO, then the RTT-scaled estimate.
Morph's proxy emulates exactly that (and never corrupts bytes).

- **Latency alone (120 ms RTT):** every request costs 80 + 120 = 200 ms. Eight
  waves through two slots, ~1.7 s. Inside the deadline.
- **Loss alone (18 %):** a stall is 200 ms. 80 + 200 = 280 ms still fits inside
  the 500 ms read timeout, so the request arrives a little late. No retry, no
  slot held. Batch 0.9 to 2.5 s.
- **Both:** the stall is 3 x 120 = 360 ms, and 200 + 360 = 560 ms is PAST the
  read timeout. Every single loss now burns a full 500 ms of a pool slot, the
  retry goes back through the queue, and eight waves cascade past 2.8 s.

`--fixed` sizes the pool to the batch: no request waits behind a stalled one,
so each request's retries are its own problem and the batch finishes in the
time of its slowest request (0.7 to 2.2 s), not the sum.

## Run it

```bash
python -m apps.pool_retry run           # baseline: PASS
python -m apps.pool_retry test          # machine mode
python -m apps.pool_retry run --fixed   # pool sized to the batch

# the condition, exactly as Morph's runtime hands it over
MORPH_NET_LATENCY_MS=120 MORPH_NET_PACKET_LOSS_PCT=18 python -m apps.pool_retry test
MORPH_NET_LATENCY_MS=120 MORPH_NET_PACKET_LOSS_PCT=18 MORPH_SEED=4 python -m apps.pool_retry test   # reproducible loss pattern

# through Morph
morph run -p ../../profiles/flagship.json -c "python -m apps.pool_retry test"
morph demo
```

Exit codes: `0` pass, `1` engineered failure (`DeadlineExceeded`), `2` setup error.

## Conditions are real, not simulated

Latency and loss are injected by Morph's own user-space TCP proxy
(`morph/runtime/adapters/proxy.py`), started in front of the server when
either knob is set (`apps/netshape.py`). The proxy is a delay line:

- `latency_ms` is a **round-trip** time; half is added per direction, chunks are
  pipelined, so latency never caps throughput;
- a lost chunk is delivered **late**, after the stall above (doubling on
  consecutive losses), in order; nothing is dropped or corrupted;
- `MORPH_SEED` makes the loss pattern reproducible.

The server sends its whole response in one write so each request is exactly
two proxy chunks (request up, response down), which makes the per-request loss
probability a function of the loss rate rather than of socket timing.

## Tuning knobs

| Var | Default | Meaning |
|---|---|---|
| `MORPH_B_N` | `16` | concurrent requests in the batch |
| `MORPH_B_POOL` | `2` | connection pool slots (`--fixed` uses `MORPH_B_N`) |
| `MORPH_B_DEADLINE` | `2.8` | whole-batch wall-clock budget (s) |
| `MORPH_B_REQ_TIMEOUT` | `0.5` | per-request read timeout (s) |
| `MORPH_B_RETRIES` | `5` | retries per request |
| `MORPH_B_SERVER_DELAY` | `0.08` | server response time (s) |
| `MORPH_B_PROXY_LATENCY_MS` | unset | per-app override of `MORPH_NET_LATENCY_MS` |
| `MORPH_B_PROXY_LOSS_PCT` | unset | per-app override of `MORPH_NET_PACKET_LOSS_PCT` |

## How the operating point was chosen

Measure each leg's duration **with the deadline disabled** (`MORPH_B_DEADLINE=99`),
then place the deadline in the gap. Measured at 120 ms / 18 %, 20 runs per
leg, this proxy:

| leg | fail | min | median | max |
|---|---|---|---|---|
| baseline | 0/20 | 694 | 706 | 720 ms |
| latency alone | 0/20 | 1681 | 1701 | 1711 ms |
| loss alone | 0/20 | 927 | 1869 | 2508 ms |
| `--fixed`, both | 0/20 | 716 | 1229 | 2237 ms |
| **both** | **19/20** | 2206 | 3731 | 4509 ms |

Everything that must pass tops out around **2.5 s**; the combined leg's median
is **3.7 s**. The deadline sits at **2.8 s**. The one combined run that passed
finished at 2.7 s: a lucky loss pattern with few stalls. That is what an 18 %
loss rate looks like, and why the acceptance bar is > 80 %, not 100 %.

### The three knobs that matter

- **Read timeout vs stall.** The interaction exists because `80 + 200` fits
  inside the read timeout and `200 + 360` does not. Move `MORPH_B_REQ_TIMEOUT`
  below 280 ms and loss alone starts failing; above 560 ms and the pair stops
  failing.
- **N / POOL** is the amplification. Eight waves turn one stalled slot into a
  cascade; `--fixed` sets it to one wave.
- **Retries** protect the `--fixed` and loss-alone legs. A request dies only if
  every attempt is lost (probability `q^(retries+1)` with `q` = 1 - 0.82^2 =
  0.33 per attempt); five retries make that negligible while the pooled
  variant still pays a read timeout per retry.

Raise loss to strengthen the interaction; raise retries to keep the other legs
clean; keep the read timeout between the two stall sizes.

## Verification status

| | status |
|---|---|
| 2x2 plus fix, `MORPH_NET_*` hand-off, 20 trials per leg | **verified** (table above) |
| Same, end to end through `morph experiment -p profiles/flagship.json` (sequential, 12 rounds max) | **verified**: baseline 0/12, `latency_only` 0/12, `loss_only` 0/12, `full_treatment` 9/9 and stopped early at E = 102 (anytime p = 0.0098); verdict `environment_caused`. With `--fixed`: every leg 0/12, verdict `no_effect` |
| Same via OS-native shaping (`tc netem` on the Pi) | not yet measured |

## Self-check

```bash
pytest apps/pool_retry/test_app.py                 # contract tier: seeded fail, seeded fixed pass, JSON line
pytest apps/pool_retry/test_app.py -m slow         # the 2x2 and the fix, 12 trials per leg, binomial bounds
```
