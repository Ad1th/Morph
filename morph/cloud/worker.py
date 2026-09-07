"""SSH transport to a remote worker.

The worker runs the SAME `morph run` against the SAME profile JSON. That is the
whole design: there is no second execution engine to keep in step, so a fix to
the adapters or the telemetry collector reaches cloud runs the moment the
worker's checkout is updated.

Nothing here is provider-specific. A GCP instance, the Pi on the desk and a
laptop across the room are all "a box you can SSH into"; `provider` in the
config is provenance, not a code path.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
from dataclasses import dataclass

from morph.schema.config import CloudConfig
from morph.schema.profile import EnvironmentProfile
from morph.schema.telemetry import RunResult

# One line, no embedded newlines: this has to survive being nested inside an
# ssh command string.
# Reports capacity as well as readiness: the parameter catalog needs the
# worker's real cores and RAM to bound its sliders, and asking for them here
# keeps that to the one round trip `check` already pays for.
_PROBE_PY = """
import json, os, sys, importlib.util as u
try:
    mb = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") // (1024 * 1024)
except (ValueError, AttributeError, OSError):
    mb = 0
# Physical cores, to match what profile.cpu.cores means. On a cloud VM the two
# differ: a GCP vCPU is a hyperthread, so an 8-vCPU box has 4 physical cores.
try:
    import psutil
    cores = psutil.cpu_count(logical=False) or os.cpu_count() or 0
except Exception:
    cores = os.cpu_count() or 0
print(json.dumps({
    "py": sys.version.split()[0],
    "morph": u.find_spec("morph") is not None,
    "cores": cores,
    "logical": os.cpu_count() or 0,
    "memory_mb": mb,
}))
"""


def _remote_path(path: str) -> str:
    """Quote a remote path, but let a leading ~ still expand.

    shlex.quote("~/morph") yields '~/morph', and `cd '~/morph'` fails: the
    shell does not expand a tilde inside quotes. Hand the expansion to $HOME
    and quote only the remainder.
    """
    if path == "~":
        return '"$HOME"'
    if path.startswith("~/"):
        rest = path[2:]
        return f'"$HOME"/{shlex.quote(rest)}' if rest else '"$HOME"'
    return shlex.quote(path)


class WorkerUnavailable(RuntimeError):
    """The worker is not configured, not reachable, or not usable."""


@dataclass
class WorkerInfo:
    """What a probe found on the far end."""

    reachable: bool
    python_version: str = ""
    morph_importable: bool = False
    can_shape_network: bool = False
    detail: str = ""
    # What the box physically has. 0 means "not learned", never "none":
    # an unreachable worker must not read as a machine with no CPUs.
    cores: int = 0          # physical
    logical: int = 0        # hyperthreads, for display only
    memory_mb: int = 0

    @property
    def usable(self) -> bool:
        return self.reachable and self.morph_importable


def resolve_config(config: CloudConfig | None) -> CloudConfig:
    """Fill a config from the environment, so credentials need not be committed."""
    cfg = (config or CloudConfig()).model_copy(deep=True)
    cfg.host = cfg.host or os.environ.get("MORPH_CLOUD_HOST")
    cfg.user = cfg.user or os.environ.get("MORPH_CLOUD_USER")
    cfg.ssh_key = cfg.ssh_key or os.environ.get("MORPH_CLOUD_SSH_KEY")
    if os.environ.get("MORPH_CLOUD_HOST"):
        cfg.enabled = True
    return cfg


class RemoteWorker:
    """Runs Morph commands on another machine over SSH."""

    def __init__(self, config: CloudConfig | None = None) -> None:
        self.config = resolve_config(config)

    # ---------------------------------------------------------------- wiring

    @property
    def configured(self) -> bool:
        return bool(self.config.host)

    @property
    def target(self) -> str:
        if not self.config.host:
            raise WorkerUnavailable(
                "No worker host. Set cloud.host in morph.yaml or MORPH_CLOUD_HOST."
            )
        return f"{self.config.user}@{self.config.host}" if self.config.user else self.config.host

    def ssh_argv(self, remote_command: str) -> list[str]:
        """Full ssh argv for `remote_command`.

        Exposed so tests can assert on the command without opening a connection.
        """
        argv = [
            "ssh",
            # Never prompt. A password prompt waiting on stdin in the middle of
            # a demo is indistinguishable from a hang.
            "-o",
            "BatchMode=yes",
            "-o",
            f"ConnectTimeout={int(self.config.connect_timeout)}",
            "-o",
            "StrictHostKeyChecking=accept-new",
        ]
        if self.config.ssh_key:
            argv += ["-i", os.path.expanduser(self.config.ssh_key)]
        argv += [self.target, remote_command]
        return argv

    def _ssh(
        self, remote_command: str, stdin: str | None = None, timeout: float = 60.0
    ) -> subprocess.CompletedProcess:
        try:
            return subprocess.run(
                self.ssh_argv(remote_command),
                input=stdin,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except FileNotFoundError as exc:
            raise WorkerUnavailable("ssh is not installed on this machine") from exc
        except subprocess.TimeoutExpired as exc:
            raise WorkerUnavailable(f"worker did not answer within {timeout:.0f}s") from exc

    # ----------------------------------------------------------------- probe

    def probe_command(self) -> str:
        """Shell run by `check`. Separate so a test can read it."""
        return (
            f"{shlex.quote(self.config.python)} -c {shlex.quote(_PROBE_PY)} 2>/dev/null; "
            # tc lives in /sbin, which is frequently absent from a non-login PATH.
            "(sudo -n /sbin/tc qdisc show dev lo >/dev/null 2>&1 && echo TC_OK || echo TC_NO)"
        )

    def check(self) -> WorkerInfo:
        """Confirm the worker can do the job before a run depends on it.

        Tests the three things that break a cloud demo, in the order they break
        it: the box answers, Morph is installed on it, and it can shape the
        network -- which needs root, and is the one mechanism PRD section 39
        calls the demo's single point of failure.
        """
        if not self.configured:
            return WorkerInfo(reachable=False, detail="no host configured")

        proc = self._ssh(self.probe_command(), timeout=self.config.connect_timeout + 15)
        if proc.returncode != 0 and not proc.stdout.strip():
            last = (proc.stderr or "").strip().splitlines()
            return WorkerInfo(
                reachable=False, detail=(last[-1][:200] if last else "ssh failed")
            )

        info = WorkerInfo(reachable=True, can_shape_network="TC_OK" in proc.stdout)
        payload = _last_json_object(proc.stdout)
        if payload:
            info.python_version = str(payload.get("py", ""))
            info.morph_importable = bool(payload.get("morph"))
            info.cores = int(payload.get("cores") or 0)
            info.logical = int(payload.get("logical") or 0)
            info.memory_mb = int(payload.get("memory_mb") or 0)

        if not info.morph_importable:
            info.detail = f"morph is not importable under {self.config.python} on the worker"
        elif not info.can_shape_network:
            info.detail = "no passwordless `sudo tc`: network shaping will not work there"
        return info

    # ------------------------------------------------------------------- run

    def build_run_command(self, command: str, timeout: float) -> str:
        """The shell run on the worker. The profile arrives on stdin.

        A temp file rather than a pipe because `morph run` takes a profile
        PATH; the trap removes it even when the run fails, so repeated trials
        cannot litter the worker.
        """
        return (
            "set -eu; "
            'f="$(mktemp)"; '
            "trap 'rm -f \"$f\"' EXIT; "
            'cat > "$f"; '
            f"cd {_remote_path(self.config.workdir)} 2>/dev/null || true; "
            f"{shlex.quote(self.config.python)} -m morph.cli.main run "
            f'--profile "$f" --command {shlex.quote(command)} '
            f"--timeout {float(timeout):g} --json"
        )

    def run(
        self,
        profile: EnvironmentProfile,
        command: str,
        timeout: float = 30.0,
    ) -> RunResult:
        """Execute `command` under `profile` on the worker; return its RunResult."""
        proc = self._ssh(
            self.build_run_command(command, timeout),
            stdin=profile.model_dump_json(),
            # Room for SSH setup and the worker's own overhead on top of the
            # run's own timeout, so a slow link is not counted as a failed trial.
            timeout=timeout + self.config.connect_timeout + 30,
        )

        payload = _last_json_object(proc.stdout)
        if payload is None:
            raise WorkerUnavailable(
                "worker returned no run result. "
                f"exit={proc.returncode} stderr={(proc.stderr or '').strip()[:300]}"
            )
        return RunResult.model_validate(payload)


def _last_json_object(text: str) -> dict | None:
    """Last JSON object printed on stdout, ignoring any banner above it."""
    for line in reversed((text or "").splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    return None
