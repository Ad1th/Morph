# Demo profiles

One `EnvironmentProfile` per demo condition. Each requests exactly one thing
(status `requested`); everything else is a captured host value from the Mac
the corpus was measured on, with locale and timezone neutralised to `C.UTF-8`
/ `UTC` so a profile never carries the demo machine's own locale into a trial.

| Profile | Requests | App it breaks | Command |
|---|---|---|---|
| `flagship.json` | `network.latency_ms` 120 (RTT) **and** `network.packet_loss_percent` 18 | `apps/pool_retry` | `morph run -p profiles/flagship.json -c "python -m apps.pool_retry test"` |
| `high_latency.json` | `network.latency_ms` 120 | `apps/timeout` | `... -c "python -m apps.timeout test"` |
| `locale_de.json` | `locale.locale` de_DE.UTF-8 | `apps/locale_parse` | `... -c "python -m apps.locale_parse test"` |
| `tz_dst.json` | `locale.timezone` America/Sao_Paulo | `apps/tz_dst` | `... -c "python -m apps.tz_dst test"` |
| `fd_limit.json` | `process.fd_limit` 64 | `apps/fd_limit` | `... -c "python -m apps.fd_limit test"` |
| `race_yield.json` | `env_vars.MORPH_C_YIELD_EVERY` 2 | `apps/race` | `... -c "python -m apps.race test"` |

Every one of these exits 1 through `morph run` on a laptop with no root, and
the same command without `-p` exits 0. `morph demo` runs the flagship 2x2 in
sequential mode without needing the file.

The `os` / `cpu` / `memory` sections are this Mac's (`darwin`, arm64, 8 cores,
16 GB). On another host they reconcile to `unavailable` for the OS family,
which is honest and harmless for a local run; with a worker configured and
`--cloud`, an OS mismatch is a shortfall and the run would be routed. To
regenerate for your own host:

```bash
morph define -t high-latency -o profiles/flagship.json     # captures your host + 120 ms / 18 %
```

or, for the others, capture with `morph capture -o base.json` and set the one
`requested` field by hand.
