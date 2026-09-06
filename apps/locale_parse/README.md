# Failure D: locale-dependent number parsing

**Trigger:** the process locale's numeric convention (`LANG` / `LC_ALL` / `LC_NUMERIC`,
or `--locale`).
**Baseline (`de_DE`):** 0% fail.
**Under condition (`en_US`):** 100% fail.
**Classification:** environment-caused.
**Fix:** parse the value's own documented format instead of the ambient locale's --
`locale.atof(raw)` becomes `float(raw.replace(",", "."))`.

## Why this one matters in the demo

It does **not** crash. The config value `"1,5"` (one and a half) is read as **15.0**
under a period-decimal locale, because the comma is treated as a thousands
separator. A 10x error, no exception, no stack trace -- silent data corruption
that only a wrong *value* reveals. It is also fully deterministic: no timing, no
randomness, no network, so it is the most reliable app in the corpus.

```
de_DE.UTF-8   decimal_point=','   atof("1,5") -> 1.5     correct
en_US.UTF-8   decimal_point='.'   atof("1,5") -> 15.0    silently wrong
```

## Run it

```bash
# baseline: passes
python -m apps.locale_parse run --locale de_DE

# condition: fails
python -m apps.locale_parse run --locale en_US

# the fix survives the condition
python -m apps.locale_parse run --fixed --locale en_US

# machine mode
python -m apps.locale_parse test --locale en_US
```

Exit codes: `0` pass, `1` engineered failure, `2` invalid trial (locale unavailable).

## How Morph should drive it

Either knob works on all three platforms:

```bash
LC_ALL=en_US.UTF-8 python -m apps.locale_parse test      # env (Linux/macOS/Windows)
python -m apps.locale_parse test --locale en_US           # explicit arg
```

faultyapps.md section 6 notes that Windows ignores `LANG`/`LC_ALL` because
`setlocale(LC_ALL, "")` reads OS settings and changing those needs a reboot.
This app works around that: it *reads* the environment variable itself and
applies the locale explicitly, so the env knob is honoured on Windows too. The
`--locale` flag remains as a backup.

## The false-evidence guard

Windows' CRT accepts any name shaped like `ll_CC` -- `setlocale(LC_ALL, "zz_ZZ")`
**succeeds** and silently leaves a period-decimal default in place. A Pi Lite
image with no generated locales can behave the same way. Left unchecked, a
locale that never applied would produce a FAIL, and Morph would report "locale
caused this failure" on evidence that was fabricated.

So the app never trusts `setlocale`'s return value. Each registered locale
declares the `decimal_point` it must produce, and the app verifies it after
applying. Mismatch, or an unregistered locale, means **exit 2 -- invalid trial**,
which Morph discards rather than counting.

Add new locales to `_LOCALES` in `app.py` along with their expected convention.

## Tuning knobs

| Var | Default | Meaning |
|---|---|---|
| `MORPH_D_LOCALE` | unset | locale to apply explicitly |
| `MORPH_D_RAW` | `1,5` | the raw config value to parse |
| `MORPH_D_EXPECTED` | `1.5` | the correct parsed value |

## Setup note for the Pi

The Raspberry Pi Lite image ships almost no locales. Generate them before
running, or every trial returns exit 2:

```bash
sudo sed -i 's/# de_DE.UTF-8/de_DE.UTF-8/' /etc/locale.gen
sudo sed -i 's/# en_US.UTF-8/en_US.UTF-8/' /etc/locale.gen
sudo locale-gen
locale -a          # verify
```
