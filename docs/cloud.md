# Cloud execution

> When this machine cannot honour a profile, hand the run to one that can. Only when you ask.

## Why it exists

PRD §10 sets the rule this feature enforces:

```
Requested: 16 GB RAM
Local:      8 GB RAM
Result:    NOT_REPRODUCIBLE_LOCALLY
```

Morph never fakes hardware equivalence. A laptop with 8 GB does not pretend to
be a 16 GB machine. So when a profile exceeds the host there are only two
honest outcomes: run it somewhere that fits, or say plainly that it cannot be
reproduced. This module is the first of those.

Cloud is a **fallback, not a default** (PRD §25: *"Do not run every experiment
in the cloud"*). A run leaves the machine only when **both** hold: you passed
`--cloud`, and staying would mean lying about the environment. A configured
worker never changes a plain `morph run`.

## Correction to the PRD and the older architecture notes

Both named **Tin Computer** as the cloud execution target, and the config once
shipped `provider: "tin"` with an `endpoint`. That endpoint does not exist:
Tin Computer is a marketing-automation product with no VMs, no containers, no
compute API and no root. It cannot host a Morph worker.

The implementation targets a plain SSH-reachable Linux box. The reference
workers are a GCP instance (`scripts/setup_gcp_worker.sh`) and the Raspberry Pi
on the desk; the code path is identical.

## How it works

The worker runs **the same `morph run`** against **the same profile JSON**:

```
local morph  --ssh-->  worker: morph run --profile <stdin> --command ... --json
             <-------  RunResult as one JSON document
```

There is deliberately no second execution engine. A fix to the adapters or the
telemetry collector reaches cloud runs the moment the worker's checkout is
updated, and a cloud result is directly comparable with a local one because
the same code produced both: the returned `RunResult` carries the worker's
`host_fingerprint`, `adapter`, `fidelity` map and `morph_version`, so a
mismatch is visible instead of silent.

| Module | Job |
|---|---|
| `morph/cloud/capability.py` | Does the profile exceed this host, and would another machine fix it? |
| `morph/cloud/worker.py` | SSH transport: probe the worker, run a profile on it |
| `morph/cloud/dispatch.py` | Choose local, remote, or an honest refusal (`NotReproducibleAnywhere`) |

### What counts as needing a worker

Only shortfalls a **different machine** would genuinely fix:

- `memory.total_mb` greater than this host's RAM (2 % tolerance for rounding)
- `cpu.cores` greater than this host's logical cores
- `cpu.architecture` this host does not have
- `os.family` this host is not

Locale, timezone, process limits and network shaping are deliberately **not**
shortfalls. Those are the adapters' business, and every adapter reports what it
could and could not do per field (`reproduced`, `approximated`,
`unavailable`). Treating them as shortfalls would send every shaped run to a
worker.

## Configuration

Nothing is required until a worker exists. One `cloud:` block in `morph.yaml`;
the committed file keeps `host` and `user` **blank** so unit tests and CI never
open an SSH connection:

```yaml
cloud:
  provider: ssh                       # provenance only: ssh | gcp | pi
  host: ""                            # set from the environment, below
  user: ""
  python: ~/morph/.venv/bin/python    # interpreter on the worker
  workdir: ~/morph                    # Morph checkout on the worker
```

Point Morph at a worker from the environment; the environment wins over the
file either way, so credentials never land in git:

```bash
export MORPH_CLOUD_HOST=34.10.20.30      # or rbpi.local
export MORPH_CLOUD_USER=morph
export MORPH_CLOUD_SSH_KEY=~/.ssh/morph_gcp   # optional
```

`MORPH_WORKER_HOST` / `MORPH_WORKER_USER` / `MORPH_WORKER_SSH_KEY` are accepted
as aliases. Setting a host from the environment also marks the worker
`enabled`.

`MORPH_NO_NETWORK=1` is the guard for tests and air-gapped demos: every SSH
attempt fails fast with `WorkerUnavailable`, `morph cloud` refuses to probe,
and `morph doctor` skips the worker check. `tests/conftest.py` sets it.

## Using it

```bash
# Does this host fall short of the profile, and is a worker ready?
morph cloud --profile target.json

# Run, routing to the worker ONLY if this host cannot satisfy the profile
morph run --profile target.json --command "pytest -q" --cloud

# Host health, including the worker probe (skipped under MORPH_NO_NETWORK)
morph doctor
```

`morph cloud` probes the three things that break a cloud demo, in the order
they break it: the box answers, Morph imports on it, and it can shape the
network. That last one needs passwordless `sudo tc` and is the single
mechanism PRD §39 calls the demo's point of failure; check it before you rely
on it.

Exit codes for `morph run --cloud`: `0` passed, `1` the run failed, `2`
`NOT_REPRODUCIBLE_LOCALLY`: the host fell short and no worker could take it.

## Setting up a worker

Requirements come from PRD §25 (2 to 4 vCPU, 8 to 16 GB RAM, 30 to 50 GB
disk, Linux), plus one this project adds: **root**, because `tc netem` and
cgroups need it. That rules out serverless and PaaS; it must be a real VM or a
real board.

### GCP

```bash
gcloud compute instances create morph-worker \
  --machine-type=e2-standard-4 \
  --image-family=ubuntu-2204-lts --image-project=ubuntu-os-cloud \
  --boot-disk-size=50GB

# from your machine: bootstrap it over SSH, nothing to copy first
ssh -i ~/.ssh/morph_gcp morph@<ip> 'bash -s' < scripts/setup_gcp_worker.sh
```

The script is idempotent and does four things in the order that matters:

1. system packages, including `iproute2` (`tc`) and `python3-venv`;
2. the Morph checkout and its dependencies in a venv (`~/morph/.venv`);
3. passwordless `sudo tc` (`/etc/sudoers.d/morph-tc`), without which shaping
   silently cannot run, plus an **opt-in delegated cgroup**: it creates
   `/sys/fs/cgroup/morph`, hands it to the worker user and enables the `cpu`
   and `memory` controllers. Morph only ever writes `cpu.max` / `memory.max`
   into a cgroup it was explicitly pointed at, so export
   `MORPH_CGROUP_PATH=/sys/fs/cgroup/morph` on the worker to have CPU quota and
   memory profiles `reproduced` there instead of hinted;
4. a self-check that **proves shaping works** (apply and remove a `netem`
   delay on `lo`) and that `morph` imports. The worker is not "ready" until
   step 4 passes.

Two choices worth making deliberately:

- **Pick a machine larger than the demo laptop.** The motivating example is
  "requested 16 GB, local 8 GB"; a worker with less RAM than the laptop makes
  the fallback pointless.
- **Pick x86_64.** Morph's profile carries `cpu.architecture`, and running an
  x86_64 target on an ARM worker is exactly the case that must be marked
  `UNAVAILABLE`.

### Raspberry Pi

The same script works on Raspberry Pi OS (Debian). Two extras the Pi Lite
image needs for the corpus: generate locales (`de_DE.UTF-8`, `en_US.UTF-8`,
`en_IN.UTF-8`) and install `tzdata`. The Pi is the reference host for the
`apps/race` fixture under a **real** cgroup CPU quota, which macOS cannot
supply; point `MORPH_CLOUD_HOST=rbpi.local` at it and run with `--cloud` and a
profile whose `cpu.quota_percent` the laptop cannot honour.

Verify the one thing that actually sinks this before building on it:

```bash
ssh morph@<ip> 'sudo -n /sbin/tc qdisc add dev lo root netem delay 100ms && \
                sudo -n /sbin/tc qdisc del dev lo root && echo SHAPING_OK'
```
