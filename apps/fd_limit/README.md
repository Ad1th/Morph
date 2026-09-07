# Failure E: connection-pool exhaustion under a lowered descriptor limit

**Trigger:** `RLIMIT_NOFILE`, the per-process file-descriptor limit (`process.fd_limit` in the profile; `ulimit -n` in a shell).
**Baseline (host limit, 256 or more):** 0/10 fail; 48 requests hold ~110 descriptors.
**Under condition (`fd_limit = 64`):** 10/10 fail with `EMFILE` at request 31. Flips between 96 (fails at request 47) and 112 (passes).
**Classification:** environment-caused (a resource limit).
**Fix:** reuse the idle keep-alive connection instead of opening a new one per request (`--fixed`): 0/10 fail under the condition, 1 pooled connection.

## Why this app exists

It is the non-network knob Morph can apply on a laptop with **no root**.
Lowering a soft `RLIMIT_NOFILE` needs no privileges on macOS or Linux, and
Morph's collector does it in the child before `exec`
(`morph/telemetry/collector.py`, `_limit_resources`). So the whole loop, run,
experiment, threshold, replay, works for a resource limit the same way it works
for latency, and the demo is not "network or nothing".

It is also a very common production failure: a container or a hardened
service unit (`LimitNOFILE=64`, `ulimit -n 256`) with a pool that never reaps.

## Mechanism

A keep-alive line server on localhost. The client's "pool" opens a fresh
connection for every request and never closes one (the leak). In this
single-process fixture each pooled connection costs **two** descriptors, the
client socket and the server's accepted socket, so 48 requests hold ~96
sockets plus stdio, the listener and Python's own handles: ~110 total.

Under a limit of 64 the client's `socket()` raises `EMFILE` ("Too many open
files", errno 24) at request 31. When the limit bites on the server's
`accept()` instead, the connection sits unanswered in the listen backlog; the
client's read times out and the app reports the same `EMFILE` signal after
confirming the descriptor table is full.

Below 16 descriptors the process cannot hold stdio, the listener and one
connection at once, so the app exits **2** (`LimitTooLowToRun`): the
environment cannot run it at all, which is an invalid trial, not evidence.

## Run it

```bash
python -m apps.fd_limit run                     # baseline: PASS
python -m apps.fd_limit test                    # machine mode
python -m apps.fd_limit run --fixed             # pool reuses its idle connection

# the condition, exactly as Morph applies it (setrlimit before the app starts)
python -c 'import resource,runpy,sys; resource.setrlimit(resource.RLIMIT_NOFILE,(64,64)); sys.argv=["x","test"]; runpy.run_module("apps.fd_limit", run_name="__main__")'

# through Morph
morph run -p ../../profiles/fd_limit.json -c "python -m apps.fd_limit test"     # exit 1
morph run -c "python -m apps.fd_limit test"                                      # exit 0
```

Exit codes: `0` pass, `1` engineered failure (`EMFILE`), `2` invalid trial (`LimitTooLowToRun`, `ServerStartFailed`).

## Measured

| soft limit | outcome |
|---|---|
| 8 | exit 2, `LimitTooLowToRun` |
| 32 | FAIL at request 15 |
| 48 | FAIL at request 23 |
| 64 | FAIL at request 31 (the profile's value) |
| 96 | FAIL at request 47 |
| 112 | PASS |
| 256 and up | PASS |

The failing request is about `(limit - 12) / 2`; the boundary for a 48-request
batch is ~104 descriptors.

## Tuning knobs

| Var | Default | Meaning |
|---|---|---|
| `MORPH_E_REQUESTS` | `48` | requests in the batch (descriptors needed ~ 2N + 12) |
| `MORPH_E_TIMEOUT_S` | `2.0` | per-request socket timeout |
| `MORPH_E_MIN_FDS` | `16` | soft limit below which the trial is invalid |

## Threshold search

`morph threshold` assumes failure *increases* with the parameter (`--low` is
safe, `--high` fails). For `process.fd_limit` the direction is reversed: low
values fail. Until the engine accepts an inverted bracket, search this one by
hand from the table above, or sweep it with `morph run` at a few limits.

## Windows

`RLIMIT_NOFILE` is POSIX; Morph ignores `fd_limit` on Windows and the app then
runs unconstrained (baseline). The condition-dependent tests skip there.

## Self-check

```bash
pytest apps/fd_limit/test_app.py
```
