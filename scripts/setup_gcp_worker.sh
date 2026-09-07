#!/usr/bin/env bash
# Bootstrap a Morph cloud worker (GCP, or any SSH-reachable Linux box).
#
# Run it from your machine, piping it in over SSH -- nothing to copy first:
#
#     ssh -i ~/.ssh/morph_gcp USER@HOST 'bash -s' < scripts/setup_gcp_worker.sh
#
# Idempotent: safe to re-run after a failure or to update the checkout.
#
# What it sets up, in the order that matters:
#   1. system packages, including iproute2 -- `tc` is the network shaping tool
#   2. the Morph checkout and its dependencies, in a venv
#   3. passwordless `sudo tc`, without which shaping silently cannot run
#   4. a self-check that proves shaping actually works on this box
#
# Step 4 is the point of the whole script. PRD section 39 calls network shaping
# the demo's single point of failure, so the worker is not "ready" until it has
# been shown to shape, not merely to accept the packages.

set -euo pipefail

REPO="${MORPH_REPO:-https://github.com/Ad1th/Morph.git}"
BRANCH="${MORPH_BRANCH:-main}"
WORKDIR="${MORPH_WORKDIR:-$HOME/morph}"

say() { printf '\n\033[36m==> %s\033[0m\n' "$1"; }
ok()  { printf '    \033[32mok\033[0m  %s\n' "$1"; }
bad() { printf '    \033[31mFAIL\033[0m %s\n' "$1"; }

say "1/4  System packages"
if command -v apt-get >/dev/null 2>&1; then
  sudo apt-get update -qq
  # iproute2 provides tc; python3-venv is separate from python3 on Debian.
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
    python3 python3-pip python3-venv git iproute2 >/dev/null
elif command -v dnf >/dev/null 2>&1; then
  sudo dnf install -y -q python3 python3-pip git iproute >/dev/null
else
  bad "no apt-get or dnf; install python3, pip, git and iproute2 yourself"
  exit 1
fi
ok "python3 $(python3 -V 2>&1 | cut -d' ' -f2), git, iproute2"

say "2/4  Morph checkout and dependencies"
if [ -d "$WORKDIR/.git" ]; then
  git -C "$WORKDIR" fetch --quiet origin "$BRANCH"
  git -C "$WORKDIR" checkout --quiet "$BRANCH"
  git -C "$WORKDIR" reset --hard --quiet "origin/$BRANCH"
  ok "updated $WORKDIR to origin/$BRANCH"
else
  git clone --quiet --branch "$BRANCH" "$REPO" "$WORKDIR"
  ok "cloned $REPO into $WORKDIR"
fi

# A venv, so the worker's Python matches what Morph's interpreter pinning
# expects and system packages are left alone.
if [ ! -d "$WORKDIR/.venv" ]; then
  python3 -m venv "$WORKDIR/.venv"
fi
"$WORKDIR/.venv/bin/pip" install --quiet --upgrade pip
"$WORKDIR/.venv/bin/pip" install --quiet -r "$WORKDIR/requirements.txt"
ok "dependencies installed in $WORKDIR/.venv"

say "3/4  Passwordless sudo for tc"
# Morph shapes the network with `tc`, which needs root. An interactive sudo
# prompt would hang a non-interactive SSH run forever, so grant just this one
# command rather than leaving the trial to stall.
TC_BIN="$(command -v tc || echo /sbin/tc)"
RULE="$(whoami) ALL=(ALL) NOPASSWD: $TC_BIN"
if ! sudo grep -qsF "$RULE" /etc/sudoers.d/morph-tc 2>/dev/null; then
  echo "$RULE" | sudo tee /etc/sudoers.d/morph-tc >/dev/null
  sudo chmod 0440 /etc/sudoers.d/morph-tc
fi
ok "granted: $RULE"

say "3b/4  A delegated cgroup for CPU/RAM limits (opt-in)"
# Morph only writes cpu.max / memory.max into a cgroup it was explicitly
# pointed at (MORPH_CGROUP_PATH); it never touches the root cgroup. Create one
# owned by this user so quota/memory profiles are REPRODUCED here, not hinted.
CG="/sys/fs/cgroup/morph"
if [ -d /sys/fs/cgroup ] && [ -f /sys/fs/cgroup/cgroup.controllers ]; then
  sudo mkdir -p "$CG" 2>/dev/null || true
  sudo chown -R "$(whoami)" "$CG" 2>/dev/null || true
  if echo "+cpu +memory" | sudo tee /sys/fs/cgroup/cgroup.subtree_control >/dev/null 2>&1 \
     && [ -w "$CG/cgroup.procs" ]; then
    ok "cgroup $CG is writable; export MORPH_CGROUP_PATH=$CG before running"
  else
    bad "could not delegate $CG; CPU quota / memory limits will be env hints only"
  fi
else
  bad "no cgroup v2 at /sys/fs/cgroup; CPU quota / memory limits will be env hints only"
fi

say "4/4  Proving the box can actually shape traffic"
# The whole reason for a worker: if this fails, network experiments cannot run
# here no matter what else is installed.
if sudo -n "$TC_BIN" qdisc add dev lo root netem delay 100ms 2>/dev/null; then
  sudo -n "$TC_BIN" qdisc del dev lo root 2>/dev/null || true
  ok "netem applied and removed on lo"
else
  bad "cannot apply netem on lo -- network experiments will NOT work here"
  echo "    check that the kernel has sch_netem: sudo modprobe sch_netem"
  exit 1
fi

# And that Morph itself imports, which is what `morph cloud` probes for.
if "$WORKDIR/.venv/bin/python" -c "import morph" 2>/dev/null; then
  ok "morph imports under $WORKDIR/.venv/bin/python"
else
  bad "morph does not import; check the pip install above"
  exit 1
fi

printf '\n\033[32mWorker ready.\033[0m Point Morph at it with:\n\n'
printf '    export MORPH_CLOUD_HOST=%s\n' "$(hostname -I 2>/dev/null | awk '{print $1}')"
printf '    export MORPH_CLOUD_USER=%s\n' "$(whoami)"
printf '    export MORPH_CLOUD_SSH_KEY=~/.ssh/morph_gcp\n\n'
printf 'or, in morph.yaml (keep host/user out of a committed file):\n\n'
printf '    cloud:\n'
printf '      provider: gcp\n'
printf '      python: %s/.venv/bin/python\n' "$WORKDIR"
printf '      workdir: %s\n\n' "$WORKDIR"
printf 'Runs only leave your machine with `morph run --cloud`.\n'
printf 'Note the host above is the INTERNAL ip; use the external one from the\n'
printf 'GCP console if you are connecting from outside the VPC.\n'
