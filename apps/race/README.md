# Failure C: race condition exposed by CPU throttling

**Trigger:** CPU quota (cgroup `cpu.max`), **not** core pinning.
**Baseline (full CPU):** double-call rate `0.000` -> PASS.
**Under condition:** rate 30-60% -> FAIL.
**Classification:** environment-**EXPOSED**.
**Fix:** wrap the check-then-act in a `Lock` (`--fixed`).

## Why this app exists

It is the one fixture that forces the CAUSED vs EXPOSED distinction
([PRD §18](../../docs/Morph_PRD.md), [Design Spec §29](../../docs/Morph_Design_Spec.md)).

The bug is in the **application**: an unlocked check-then-act on a shared cache
is wrong on every machine. A calm CPU merely hides it — each thread finishes the
window before anything can preempt it. Constrain the CPU and the identical code
starts losing the race constantly.

So the correct report is:

> CPU constraint strongly increases the probability of this failure.

and **not**:

> CPU caused this bug.

Nothing about the application differs between baseline and treatment. Only the
environment does. That is precisely what entitles Morph to claim exposure rather
than causation — and it is the claim that makes the tool look technically honest
to a judge who knows the difference.

## Run it

```bash
python -m apps.race run                       # baseline: PASS
python -m apps.race test                      # machine mode
python -m apps.race run --fixed               # lock-protected
```

Exit codes: `0` pass, `1` engineered failure (race detected), `2` setup error.

## Applying the real condition

Linux / Raspberry Pi, cgroup v2:

```bash
systemd-run --scope -p CPUQuota=10% python -m apps.race test
```

or explicitly:

```bash
sudo mkdir /sys/fs/cgroup/morph
echo "10000 100000" | sudo tee /sys/fs/cgroup/morph/cpu.max    # 10% of one CPU
echo $PID | sudo tee /sys/fs/cgroup/morph/cgroup.procs
```

**Do not use `taskset`.** Core pinning is a different mechanism and can *reduce*
this race by removing true parallelism ([faultyapps.md §10](../../docs/faultyapps.md#10-pitfalls)).
Quota throttling — freezing the whole process when its budget is exhausted — is
what reliably lands inside the race window.

**macOS and Windows have no cgroups.** This condition routes to the Pi or a Linux
VM. Say so during the demo; it matches the PRD's honest-limitations framing
rather than weakening it.

## Verification status

| | status |
|---|---|
| Race exists, baseline clean, fix works | **verified here** (0/50 baseline, 50/50 under simulated condition, 0/50 fixed) |
| Real cgroup `cpu.max` exposes it | **NOT yet verified — must be measured on the Pi** |

`MORPH_C_SWITCH_INTERVAL` lowers the interpreter's thread switch interval, making
preemption frequent. That raises the chance a switch lands inside the race window
— the same *direction* of effect as a cgroup freeze — so the fixture can be
self-checked on Windows and macOS.

It is **not** equivalent to real throttling and must never stand in for it in the
demo: a cgroup quota freezes the whole process at budget exhaustion, whereas this
only changes how often the GIL is handed between threads. Treat it as a unit-test
device, and measure the real numbers on the Pi.

## Why the barrier

Thread creation on Windows costs ~50µs — far longer than the check-act window —
so sequentially started threads never overlap and the race fired **0/300 times**
in tuning. The barrier makes all threads arrive at the check together, giving the
race a real but still narrow window. The bug is genuine; the barrier only ensures
the threads actually contend.

## Tuning knobs

| Var | Default | Meaning |
|---|---|---|
| `MORPH_C_ITERS` | `300` | iterations per run |
| `MORPH_C_THREADS` | `8` | threads contending per iteration |
| `MORPH_C_SPIN` | `200` | width of the race window, in loop steps |
| `MORPH_C_MAX_RATE` | `0.05` | double-call rate above which the run FAILS |
| `MORPH_C_SWITCH_INTERVAL` | unset | verification-only throttling stand-in |

Measured tuning curve on Windows / Python 3.14 (rate of double-calls):

| threads | spin | calm (5ms) | preempted (0.5ms) |
|---|---|---|---|
| 8 | 200 | 0.000 | **0.31–0.42** |
| 4 | 200 | 0.000 | 0.18–0.22 |
| 4 | 2000 | 0.000 | 0.98 |

`threads=8, spin=200` was chosen because it lands in the doc's 30–60% target band.
If the Pi's real throttling gives a rate that is too high (reads as "always
broken") or too low, adjust `MORPH_C_SPIN` first — it moves the rate most.
