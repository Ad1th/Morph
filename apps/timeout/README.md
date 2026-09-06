# Failure A: timeout under network latency

**Trigger:** network latency injected on the loopback interface (`lo`).
**Threshold:** somewhere past ~50ms added latency (response takes ~200ms, client
deadline is 250ms) -- narrow it further with `morph threshold` once wired in.
**Baseline fail rate:** < 5% (expect ~0/50).
**Under condition fail rate:** > 90% (expect ~50/50) once added latency pushes
round-trip time past the client timeout.
**Classification:** environment-caused.
**Fix:** raise `CLIENT_TIMEOUT` — the `--fixed` flag sets it to 1.0s, comfortably
above the ~200ms response delay regardless of added latency in the demo range.

## Run it

```bash
# human-readable
python -m apps.timeout run
python -m apps.timeout run --fixed

# machine mode (JSON result line, for Morph / scripts)
python -m apps.timeout test
```

Exit codes: `0` pass, `1` engineered failure (timeout), `2` setup error.

## Tuning knobs (env vars)

| Var | Default | Meaning |
|---|---|---|
| `MORPH_A_RESP_DELAY_S` | `0.20` | server response delay (seconds) |
| `MORPH_A_TIMEOUT` | `0.25` | client timeout, unfixed variant (seconds) |
| `MORPH_A_FIXED_TIMEOUT` | `1.0` | client timeout, `--fixed` variant (seconds) |

## Manual verification protocol

See [docs/faultyapps.md section 7](../../docs/faultyapps.md#7-manual-verification-protocol)
for the full baseline/condition/teardown loop. Quick version:

```bash
# 1. baseline -- expect ~50x exit 0
for i in $(seq 1 50); do python -m apps.timeout test >/dev/null; echo $?; done | sort | uniq -c

# 2. apply latency on loopback (Linux; see docs/faultyapps.md section 6 for macOS/Windows)
sudo tc qdisc add dev lo root netem delay 180ms

# expect ~50x exit 1
for i in $(seq 1 50); do python -m apps.timeout test >/dev/null; echo $?; done | sort | uniq -c

# 3. ALWAYS remove the condition
sudo tc qdisc del dev lo root
```

## Gotcha

The server binds `127.0.0.1`. Shaping `eth0`/`wlan0` with `tc netem` does **nothing**
to loopback traffic — you must shape `dev lo` specifically (or run client and
server on separate machines and shape the real NIC). See
[docs/faultyapps.md section 10](../../docs/faultyapps.md#10-pitfalls).
