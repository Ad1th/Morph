# Failure F: "same time tomorrow" across a DST transition

**Trigger:** the process timezone (`TZ`, which every adapter exports for `locale.timezone`; or `--tz`).
**Baseline (`TZ` unset or `UTC`, or any zone without a transition that night):** 0/5 fail.
**Under condition (`TZ=America/Sao_Paulo`):** 5/5 fail with `ScheduleDrift`; `America/New_York` fails too.
**Classification:** environment-caused.
**Fix:** do calendar arithmetic on wall-clock fields and let `mktime` resolve the offset (`tm_isdst = -1`), instead of adding 86 400 seconds (`--fixed`): 0/5 fail under the condition.

## The bug

A scheduler runs a job "nightly at 23:30" and computes the next run as
`last_run_epoch + 86400`: twenty-four hours later. On almost every day in
almost every zone that is the same wall-clock time tomorrow. On the night the
zone changes its clocks the calendar day is 23 or 25 hours long, and the job
fires an hour off. When the transition sits at **midnight**, as Brazil's did,
the "tomorrow" run lands on the wrong **date**.

```
anchor                 2018-11-03 23:30 local
TZ=UTC                 next run 2018-11-04 23:30          correct
TZ=Asia/Kolkata        next run 2018-11-04 23:30          correct (no DST)
TZ=America/Sao_Paulo   DST began 2018-11-04 00:00 (00:00 became 01:00)
                       next run 2018-11-05 00:30 -02      a whole day skipped
TZ=America/New_York    DST ended 2018-11-04 02:00
                       next run 2018-11-04 22:30 EST      an hour early
```

Fully deterministic: no timing, no randomness, no network. It is the
pure-Python form of a documented real bug: moment-timezone #672 / #728 / #967
and pytz #56 ([faultyapps.md §8](../../docs/faultyapps.md#8-real-bugs-from-github)).

## Run it

```bash
python -m apps.tz_dst run                                  # host zone: PASS (unless it switched clocks that night)
TZ=UTC python -m apps.tz_dst run                           # baseline: PASS
TZ=America/Sao_Paulo python -m apps.tz_dst run             # condition: FAIL
TZ=America/Sao_Paulo python -m apps.tz_dst run --fixed     # the fix survives
python -m apps.tz_dst test --tz America/Sao_Paulo          # explicit knob

morph run -p ../../profiles/tz_dst.json -c "python -m apps.tz_dst test"   # exit 1
morph run -c "python -m apps.tz_dst test"                                  # exit 0
```

Exit codes: `0` pass, `1` engineered failure (`ScheduleDrift`), `2` invalid trial (`TimezoneUnavailable`).

## Exit 2: the false-evidence guard

libc turns an unknown `TZ` into UTC **silently**. Without a guard,
`TZ=Nowhere/Bogus` (or a host without `tzdata`) would produce a PASS credited
to a zone that was never applied. So the app resolves the requested zone with
`zoneinfo` and checks that libc's offset at the anchor agrees; if the zone is
unknown or did not take effect the trial is **exit 2**, which Morph discards.

## How Morph drives it

`profile.locale.timezone` is exported as `TZ`; the adapter marks it
`reproduced` for an IANA name and `approximated` otherwise. The app calls
`time.tzset()` after reading `TZ` (or `--tz` / `MORPH_F_TZ`) so the value is
honoured even when the interpreter started under a different zone. Windows has
no `tzset()`; the condition-dependent tests skip there.

A captured profile carries the *source* machine's zone, so replaying a
capture from a Sao Paulo laptop reproduces this failure on any host.

## Tuning knobs

| Var | Default | Meaning |
|---|---|---|
| `MORPH_F_TZ` | unset | zone to apply explicitly |
| `MORPH_F_ANCHOR` | `2018-11-03 23:30` | anchor wall-clock time, `YYYY-MM-DD HH:MM` |

## Setup note

Needs `tzdata` (`sudo apt install tzdata` on the Pi Lite image).

## Self-check

```bash
pytest apps/tz_dst/test_app.py
```
