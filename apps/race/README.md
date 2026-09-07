# Failure C: race condition exposed by CPU throttling

**Trigger:** CPU quota (cgroup `cpu.max`, Linux with root), **not** core pinning; or, root-free on any OS, the `MORPH_C_YIELD_EVERY` preemption knob.
**Baseline (full CPU):** double-call rate `0.000`, 0/10 fail.
**Under condition:** 10/10 fail; double-call rate 0.28 to 0.40 with `MORPH_C_YIELD_EVERY=2`, ~0.65 with `=1`.
**Classification:** environment-**EXPOSED**.
**Fix:** wrap the check-then-act in a `Lock` (`--fixed`): 0/10 fail, rate 0.000 under the condition.

## Why this app exists

It is the one fixture that forces the CAUSED vs EXPOSED distinction
([PRD §18](../../docs/Morph_PRD.md), [Design Spec §29](../../docs/Morph_Design_Spec.md)).

The bug is in the **application**: an unlocked check-then-act on a shared cache
is wrong on every machine. A calm CPU merely hides it: each thread finishes the
window before anything can preempt it. Constrain the CPU and the identical code
starts losing the race constantly.

So the correct report is:

> CPU constraint strongly increases the probability of this failure.

and **not**:

> CPU caused this bug.

Nothing about the application differs between baseline and treatment. Only the
environment does. That is precisely what entitles Morph to claim exposure rather
than causation, and its classifier says `environment_exposed` when the baseline
has some failures and the treatment amplifies them.

## Run it

```bash
python -m apps.race run                       # baseline: PASS
python -m apps.race test                      # machine mode
python -m apps.race run --fixed               # lock-protected

MORPH_C_YIELD_EVERY=2 python -m apps.race test              # root-free condition, any OS
morph run -p ../../profiles/race_yield.json -c "python -m apps.race test"   # same, via the profile's env_vars
```

Exit codes: `0` pass, `1` engineered failure (`RaceDetected`), `2` setup error.

## Applying the real condition (Linux)

```bash
systemd-run --scope -p CPUQuota=10% python -m apps.race test
```

or explicitly:

```bash
sudo mkdir /sys/fs/cgroup/morph
echo "10000 100000" | sudo tee /sys/fs/cgroup/morph/cpu.max    # 10 % of one CPU
echo $PID | sudo tee /sys/fs/cgroup/morph/cgroup.procs
```

Morph's Linux adapter does this itself for `profile.cpu.quota_percent` when it
has root (or a delegated cgroup via `MORPH_CGROUP_PATH`; see
`scripts/setup_gcp_worker.sh`). **Do not use `taskset`.** Core pinning is a
different mechanism and can *reduce* this race by removing true parallelism
([faultyapps.md §9](../../docs/faultyapps.md#9-pitfalls)). Quota throttling,
freezing the whole process when its budget is exhausted, is what reliably lands
inside the race window.

## The root-free knob (macOS, Windows, unprivileged Linux)

macOS and Windows have no cgroups, and Morph's adapters there export only a
`MORPH_CPU_QUOTA_PERCENT` hint that nothing enforces. So the fixture carries
its own deterministic stand-in: `MORPH_C_YIELD_EVERY=N` inserts one
`time.sleep(0)` *inside the race window* on every Nth iteration. A `sleep(0)`
hands the GIL to a waiting thread, which is exactly what a preemption landing
in the window does; the other iterations run uninterrupted. `N=1` races on
nearly every iteration, `N=2` on about half.

`profiles/race_yield.json` passes it through the profile's `env_vars`, so the
whole `morph run` / `morph experiment` loop works on a laptop.

It has the same *direction* of effect as throttling and it is honest to demo
with, provided the demo says what it is: a stand-in that makes the same
application bug visible, not a claim that macOS reproduced a CPU quota. The
real quota is measured on the Pi (`needs_linux` test below).

## Why the barrier

Thread creation costs far longer than the check-act window (~50 us on
Windows), so sequentially started threads never overlap and the race fired
**0/300 times** in tuning without one. The barrier makes all threads arrive at
the check together, giving the race a real but still narrow window. The bug is
genuine; the barrier only ensures the threads actually contend.

## Tuning knobs

| Var | Default | Meaning |
|---|---|---|
| `MORPH_C_ITERS` | `300` | iterations per run |
| `MORPH_C_THREADS` | `8` | threads contending per iteration |
| `MORPH_C_SPIN` | `200` | width of the race window, in loop steps |
| `MORPH_C_MAX_RATE` | `0.05` | double-call rate above which the run FAILS |
| `MORPH_C_YIELD_EVERY` | `0` (off) | yield inside the window on every Nth iteration |
| `MORPH_C_SWITCH_INTERVAL` | unset | interpreter thread switch interval (s); scheduler-dependent, inert on macOS |

Measured on macOS / Python 3.12 (double-call rate, 300 iterations):

| `MORPH_C_YIELD_EVERY` | rate |
|---|---|
| off | 0.000 |
| 2 | 0.28 to 0.40 |
| 1 | 0.64 |

The earlier `MORPH_C_SWITCH_INTERVAL` stand-in gave 0.31 to 0.42 on Windows /
Python 3.14 and exactly 0.000 on macOS, which is why it was replaced as the
self-test knob; it is kept as an extra.

## Verification status

| | status |
|---|---|
| Race exists, baseline clean, fix works, yield knob exposes it | **verified here** (macOS) |
| Real cgroup `cpu.max` exposes it | **not yet measured**: `pytest apps/race -m "slow and needs_linux"` on the Pi |

## Self-check

```bash
pytest apps/race/test_app.py                    # contract tier
pytest apps/race/test_app.py -m slow            # 10-trial rates; the cgroup test runs only on Linux
```
