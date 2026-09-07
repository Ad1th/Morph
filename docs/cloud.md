# Cloud execution

> When this machine cannot honour a profile, hand the run to one that can.

## Why it exists

PRD §10 sets the rule this feature enforces:

```
Requested: 16 GB RAM
Local:      8 GB RAM
Result:    NOT_REPRODUCIBLE_LOCALLY
```

Morph never fakes hardware equivalence. A laptop with 8 GB does not pretend to
be a 16 GB machine. So when a profile exceeds the host, there are only two
honest outcomes: run it somewhere that fits, or say plainly that it cannot be
reproduced. This module is the first of those.

Cloud is a **fallback, not a default** (PRD §25: *"Do not run every experiment
in the cloud"*). A run only leaves the machine when staying would mean lying
about the environment.

## Correction to the PRD and architecture doc

Both name **Tin Computer** as the cloud execution target, and
`morph/schema/config.py` previously shipped `provider: "tin"` with
`endpoint: "https://api.tin.computer/v1"`.

That endpoint does not exist. Tin Computer is an *"AI growth agent for small
SaaS teams"* that connects to GitHub, Stripe and analytics and ships marketing
pull requests. It offers no VMs, no containers, no compute API and no root. It
cannot host a Morph worker.

The implementation therefore targets a plain SSH-reachable Linux box; the
reference worker is a GCP instance. PRD §26 and architecture.md §13 should be
corrected to match.

## How it works

The worker runs **the same `morph run`** against **the same profile JSON**:

```
local morph  --ssh-->  worker: morph run --profile <stdin> --command ... --json
             <-------  RunResult as one JSON document
```

There is deliberately no second execution engine. A fix to the adapters or the
telemetry collector reaches cloud runs the moment the worker's checkout is
updated, and a cloud result is directly comparable with a local one because
the same code produced both.

| Module | Job |
|---|---|
| `morph/cloud/capability.py` | Does the profile exceed this host, and would another machine fix it? |
| `morph/cloud/worker.py` | SSH transport: probe the worker, run a profile on it |
| `morph/cloud/dispatch.py` | Choose local, remote, or an honest refusal |

### What counts as needing a worker

Only shortfalls a **different machine** would genuinely fix:

- `memory.total_mb` greater than this host's RAM
- `cpu.cores` greater than this host's logical cores
- `cpu.architecture` this host does not have
- `os.family` this host is not

Locale, timezone and network shaping are deliberately **not** shortfalls. Those
are the adapters' business, and `reconcile_profile_statuses` already reports
them honestly as `APPROXIMATED` or `UNAVAILABLE`. Treating them as shortfalls
would send every shaped run to a worker.

Memory comparison carries a 2% tolerance. The profiler and the assessment both
convert bytes to MB but round differently, and without it, capturing a profile
on a machine and immediately assessing it reported a 1 MB shortfall — routing
the run to a worker for nothing.

## Configuration

Nothing is required until a worker exists. In `morph.yaml`:

```yaml
cloud:
  enabled: true
  provider: gcp        # provenance only; transport is SSH either way
  host: 34.10.20.30    # the instance's external IP
  user: morph
  ssh_key: ~/.ssh/morph_gcp
  python: python3
  workdir: ~/morph     # the Morph checkout on the worker
```

Credentials can equally come from the environment, so the file can be
committed without them:

```bash
export MORPH_CLOUD_HOST=34.10.20.30
export MORPH_CLOUD_USER=morph
export MORPH_CLOUD_SSH_KEY=~/.ssh/morph_gcp
```

## Using it

```bash
# Does this host fall short of the profile, and is a worker ready?
morph cloud --profile target.json

# Run, routing to the worker only if this host cannot satisfy the profile
morph run --profile target.json --command "pytest -q" --cloud
```

`morph cloud` probes the three things that break a cloud demo, in the order
they break it: the box answers, Morph is installed on it, and it can shape the
network. That last one needs passwordless `sudo tc` and is the single mechanism
PRD §39 calls the demo's point of failure — check it before you rely on it.

Exit codes for `morph run --cloud`: `0` passed, `1` the run failed, `2`
`NOT_REPRODUCIBLE_LOCALLY` — the host fell short and no worker could take it.

## Setting up a GCP worker

Requirements come from PRD §25 (2–4 vCPU, 8–16 GB RAM, 30–50 GB disk, Linux),
plus one this project adds: **root**, because `tc netem` and cgroups need it.
That rules out every serverless and PaaS option; it must be a real VM.

```bash
gcloud compute instances create morph-worker \
  --machine-type=e2-standard-4 \
  --image-family=ubuntu-2204-lts --image-project=ubuntu-os-cloud \
  --boot-disk-size=50GB

# on the worker
sudo apt update && sudo apt install -y python3-pip git iproute2
git clone <this repo> ~/morph && cd ~/morph
pip install -r requirements.txt

# passwordless tc, so shaping works without an interactive sudo prompt
echo "$USER ALL=(ALL) NOPASSWD: /sbin/tc" | sudo tee /etc/sudoers.d/morph-tc
```

Two choices worth making deliberately:

- **Pick a machine larger than the demo laptop.** The motivating example is
  "requested 16 GB, local 8 GB"; a worker with less RAM than the laptop makes
  the fallback pointless.
- **Pick x86_64.** Morph's profile carries `cpu.architecture`, and running an
  x86_64 target on an ARM worker is exactly the case that must be marked
  `UNAVAILABLE` — demonstrating the honesty feature on a machine that cannot
  honestly satisfy the profile undercuts it.

Verify the one thing that actually sinks this before building on it:

```bash
ssh morph@<ip> 'sudo -n /sbin/tc qdisc add dev lo root netem delay 100ms && \
                sudo -n /sbin/tc qdisc del dev lo root && echo SHAPING_OK'
```
