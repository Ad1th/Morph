# Failure D: locale-dependent number parsing

**Trigger:** the process locale's numeric convention (`LC_ALL` / `LANG`, which the adapters export for `locale.locale`; or `--locale`).
**Baseline (no locale env, a C.UTF-8 / POSIX / en_US / en_IN shell):** 0/5 fail.
**Under condition (`de_DE.UTF-8`, or any comma-decimal locale such as `fr_FR`):** 5/5 fail.
**Classification:** environment-caused.
**Fix:** parse the value's documented format instead of the ambient locale's: `locale.atof(raw)` becomes `float(raw)`. 0/5 fail under the condition.

## Why this one matters in the demo

It does **not** crash. The config value `"1.5"` (one and a half, written the
way the developer wrote it) is read as **15.0** under a comma-decimal locale,
because the period is that locale's thousands separator and `locale.atof`
strips it. A 10x error, no exception, no stack trace: silent data corruption
that only a wrong *value* reveals. Fully deterministic, so it is the most
reliable app in the corpus.

```
C / en_US / en_IN   decimal_point='.'   atof("1.5") -> 1.5     correct
de_DE / fr_FR       decimal_point=','   atof("1.5") -> 15.0    silently wrong
```

`en_IN` is registered and passes: it shares the period-decimal convention, so
an Indian-English target is *not* a failing condition for this bug.

## Run it

```bash
python -m apps.locale_parse run                              # baseline: passes in a plain shell
LC_ALL=de_DE.UTF-8 LANG=de_DE.UTF-8 python -m apps.locale_parse run     # condition: fails
LC_ALL=de_DE.UTF-8 LANG=de_DE.UTF-8 python -m apps.locale_parse run --fixed   # the fix survives
python -m apps.locale_parse test --locale de_DE              # explicit knob (Windows path)

morph run -p ../../profiles/locale_de.json -c "python -m apps.locale_parse test"   # exit 1
morph run -c "python -m apps.locale_parse test"                                     # exit 0
```

Exit codes: `0` pass, `1` engineered failure (`LocaleParseMismatch`, or `ValueError` for a locale that rejects the string outright), `2` invalid trial.

## Exit 2 is for invalid trials only

Exit 2 means Morph discards the run rather than counting it, so it is reserved
for a trial the app could not attempt:

- an explicitly requested locale (`--locale`, `MORPH_D_LOCALE`, or an
  `LC_ALL`/`LANG` naming a locale this fixture knows) that is **not
  installed**, or
- one that `setlocale` accepted but that **did not take effect** (the
  false-evidence guard below).

An unknown *ambient* locale is not invalid. If a developer's shell says
`LANG=en_GB.UTF-8`, the app runs under en_GB and reports a real pass or fail;
turning that into a setup error would make every plain run on an unlisted
locale disappear from the evidence.

## How Morph drives it

The adapters export `LC_ALL` and `LANG` from `profile.locale.locale`
(POSIX-normalised, so `de-DE` becomes `de_DE.UTF-8`). On Windows the C runtime
ignores those variables (`setlocale(LC_ALL, "")` reads OS settings, and
changing those needs a reboot), so the app *reads the variables itself* and
applies the locale explicitly; the env knob therefore works on Windows too,
and `--locale` remains as a backup.

## The false-evidence guard

Windows' CRT accepts any name shaped like `ll_CC`: `setlocale(LC_ALL, "zz_ZZ")`
**succeeds** and silently leaves a period-decimal default in place. A Pi Lite
image with no generated locales can behave the same way. Left unchecked, a
requested locale that never applied would produce a PASS that hides the bug or
a FAIL blamed on the wrong thing.

So the app never trusts `setlocale`'s return value. Each registered locale
declares the `decimal_point` it must produce, and the app verifies it after
applying. A mismatch, or an unregistered explicit locale, is **exit 2**.

Add new locales to `_LOCALES` in `app.py` along with their expected convention.

## Tuning knobs

| Var | Default | Meaning |
|---|---|---|
| `MORPH_D_LOCALE` | unset | locale to apply explicitly |
| `MORPH_D_RAW` | `1.5` | the raw config value to parse |
| `MORPH_D_EXPECTED` | `1.5` | the correct parsed value |

## Setup note for the Pi and for CI

The Raspberry Pi Lite image and GitHub's `ubuntu-latest` ship almost no
locales. Generate them, or every de_DE trial returns exit 2 (and the corpus
tests skip the de_DE legs):

```bash
sudo sed -i 's/# de_DE.UTF-8/de_DE.UTF-8/' /etc/locale.gen
sudo sed -i 's/# en_US.UTF-8/en_US.UTF-8/' /etc/locale.gen
sudo locale-gen
locale -a          # verify
```

## Self-check

```bash
pytest apps/locale_parse/test_app.py
```
