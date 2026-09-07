# Failure A: timeout under network latency

**Trigger:** network latency, a round-trip time (`network.latency_ms`).
**Threshold:** ~42 ms RTT. Measured 0/5 at 40 ms, 7/10 at 42 ms, 5/5 at 45 ms and above (5 trials per point, 5 to 120 ms).
**Baseline fail rate:** 0/20 (~208 ms against a 250 ms deadline).
**Under condition:** 20/20 at 120 ms RTT.
**Classification:** environment-caused.
**Fix:** raise the client deadline; `--fixed` sets it to 1.0 s, comfortably above the ~200 ms response for any latency in the demo range.

## Run it

```bash
python -m apps.timeout run
python -m apps.timeout run --fixed
python -m apps.timeout test                       # machine mode (JSON result line)

MORPH_NET_LATENCY_MS=120 python -m apps.timeout test          # the condition, as Morph injects it
morph run -p ../../profiles/high_latency.json -c "python -m apps.timeout test"
```

Exit codes: `0` pass, `1` engineered failure (`TimeoutException`), `2` setup error (connection refused, protocol error: an invalid trial, never counted).

## Mechanism

A client with a 250 ms deadline calls a local server that always takes ~200 ms
to respond. Under loopback latency the response beats the deadline. Add RTT
and the response arrives late. The server never sleeps for a latency value of
its own: the delay comes from the network path exactly once (an older version
also slept `MORPH_LATENCY_MS` server-side, which triple-counted the condition
and put the flip point at 14 ms).

The **only** failure path is the deadline. Under Morph's proxy a lost packet is
delivered late after a retransmission stall of `max(200 ms, 3 x RTT)`, never
corrupted, so under packet loss this app also fails through the same deadline:
measured 3/10 at 18 % loss with no added latency (a 200 ms stall against 45 ms
of headroom). That is the correct behaviour of a tight deadline, and it is why
`pool_retry`, not this app, is the fixture that stays clean under either
variable alone.

## Tuning knobs (env vars)

| Var | Default | Meaning |
|---|---|---|
| `MORPH_A_RESP_DELAY_S` | `0.20` | server response delay (seconds) |
| `MORPH_A_TIMEOUT` | `0.25` | client deadline, unfixed variant (seconds) |
| `MORPH_A_FIXED_TIMEOUT` | `1.0` | client deadline, `--fixed` variant (seconds) |
| `MORPH_NET_LATENCY_MS` | unset | RTT to inject through Morph's proxy (set by the runtime) |
| `MORPH_NET_PACKET_LOSS_PCT` | unset | loss to inject through Morph's proxy (set by the runtime) |

### Matching the threshold to the pitch

The flip point is ~42 ms RTT: deadline 250 ms minus response ~208 ms. The
README's narrative ("100 ms PASS, 150 ms PASS, 200 ms FAIL") wants a flip near
150 to 200 ms. To put it there without touching the client, shorten the
response so the headroom is ~170 ms:

```bash
MORPH_A_RESP_DELAY_S=0.08 python -m apps.timeout test    # flips at ~170 ms RTT
```

Decide which number the demo quotes before rehearsing. Whatever it is, it is an
RTT: the profile value, the injected value and the value `morph threshold`
reports all mean round-trip.

## Threshold search

```bash
morph threshold -c "python -m apps.timeout test" --parameter network.latency_ms --low 0 --high 120
```

Probabilistic bisection (`--method bayes`, the default) returns a credible
interval around ~42 ms and the posterior it came from; `--method bisect` is
the plain majority-vote halving.

## Self-check

```bash
pytest apps/timeout/test_app.py                 # contract tier
pytest apps/timeout/test_app.py -m slow         # 20-trial rates and the two-point threshold check
```
