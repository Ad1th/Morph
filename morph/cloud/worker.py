"""SSH transport to a remote worker.

The worker runs the SAME `morph run` against the SAME profile JSON. That is the
whole design: there is no second execution engine to keep in step, so a fix to
the adapters or the telemetry collector reaches cloud runs the moment the
worker's checkout is updated.

Nothing here is provider-specific. A GCP instance, the Pi on the desk and a
laptop across the room are all "a box you can SSH into"; `provider` in the
config is provenance, not a code path.

Safety rails:

* `MORPH_NO_NETWORK=1` (set by tests/conftest.py) makes every SSH attempt
  raise `WorkerUnavailable` before a socket is opened, so a unit test can
  never reach a real machine whatever the config says.
* SSH runs with `BatchMode=yes` (never prompts) and
  `StrictHostKeyChecking=accept-new` (trust on first use, refuse a changed key).
* Anything that looks like a token is redacted from error text.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
from dataclasses import dataclass

from morph.schema.config import CloudConfig
from morph.schema.profile import EnvironmentProfile
from morph.schema.telemetry import RunResult

# One line, no embedded newlines: this has to survive being nested inside an
# ssh command string.
_PROBE_PY = (
    "import json,sys,importlib.util as u;"
    "print(json.dumps({'py':sys.version.split()[0],"
    "'morph':u.find_spec('morph') is not None}))"
)

# GitHub PATs, generic long hex/base64 secrets, and `user:secret@host` URLs.
_SECRET_RE = re.compile(
    r"(gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}"
    r"|(?<=://)[^/\s:]+:[^@\s]+(?=@)|AUTHORIZATION:\s*\S+\s+\S+)"
)


def redact(text: str) -> str:
    """Scrub anything token-shaped from text destined for a log or an exception."""
    return _SECRET_RE.sub("***", text or "")


def network_disabled() -> bool:
    return (os.environ.get("MORPH_NO_NETWORK") or "").strip().lower() in ("1", "true", "yes", "on")


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

    @property
    def usable(self) -> bool:
        return self.reachable and self.morph_importable


def _env(*names: str) -> str | None:
    for name in names:
        value = (os.environ.get(name) or "").strip()
        if value:
            return value
    return None


def resolve_config(config: CloudConfig | None) -> CloudConfig:
    """Fill a config from the environment, so credentials need not be committed.

    `MORPH_CLOUD_*` is canonical; `MORPH_WORKER_*` are accepted as aliases.
    """
    cfg = (config or CloudConfig()).model_copy(deep=True)
    cfg.host = cfg.host or _env("MORPH_CLOUD_HOST", "MORPH_WORKER_HOST")
    cfg.user = cfg.user or _env("MORPH_CLOUD_USER", "MORPH_WORKER_USER")
    cfg.ssh_key = cfg.ssh_key or _env("MORPH_CLOUD_SSH_KEY", "MORPH_WORKER_SSH_KEY")
    if _env("MORPH_CLOUD_HOST", "MORPH_WORKER_HOST"):
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
            # Trust on first use; refuse a host whose key has changed.
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
        if network_disabled():
            raise WorkerUnavailable(
                "MORPH_NO_NETWORK is set: refusing to open an SSH connection "
                f"to {self.target}"
            )
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
            f"{_remote_path(self.config.python)} -c {shlex.quote(_PROBE_PY)} 2>/dev/null; "
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

        try:
            proc = self._ssh(self.probe_command(), timeout=self.config.connect_timeout + 15)
        except WorkerUnavailable as exc:
            return WorkerInfo(reachable=False, detail=redact(str(exc))[:200])
        if proc.returncode != 0 and not proc.stdout.strip():
            last = (proc.stderr or "").strip().splitlines()
            return WorkerInfo(
                reachable=False, detail=(redact(last[-1])[:200] if last else "ssh failed")
            )

        info = WorkerInfo(reachable=True, can_shape_network="TC_OK" in proc.stdout)
        payload = _last_json_object(proc.stdout)
        if payload:
            info.python_version = str(payload.get("py", ""))
            info.morph_importable = bool(payload.get("morph"))

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
        cannot litter the worker. The worker's run is local-only by contract
        (no `--cloud`), so a worker can never recurse into another worker.
        """
        return (
            "set -eu; "
            'f="$(mktemp)"; '
            "trap 'rm -f \"$f\"' EXIT; "
            'cat > "$f"; '
            f"cd {_remote_path(self.config.workdir)} 2>/dev/null || true; "
            f"{_remote_path(self.config.python)} -m morph.cli.main run "
            f'--profile "$f" --command {shlex.quote(command)} '
            f"--timeout {float(timeout):g} --json"
        )

    def run(
        self,
        profile: EnvironmentProfile,
        command: str,
        timeout: float = 30.0,
    ) -> RunResult:
        """Execute `command` under `profile` on the worker; return its RunResult.

        Raises WorkerUnavailable -- never returns a fabricated trial -- when
        the worker produced no result, refused the profile, or could not even
        find the command (only commands relative to the worker's `workdir`,
        such as the `apps/*` demos, are routable: project files are not synced).
        """
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
                f"exit={proc.returncode} stderr={redact((proc.stderr or '').strip())[:300]}"
            )
        if "error" in payload and "exit_code" not in payload:
            # `morph run --json` prints {"error": "not_reproducible", "detail": ...}
            # on exit 2; that is a refusal, not a RunResult.
            raise WorkerUnavailable(
                f"worker refused the run: {redact(str(payload.get('detail') or payload['error']))}"
            )
        result = RunResult.model_validate(payload)
        if result.exit_code == 127 or result.error_type == "FileNotFoundError":
            raise WorkerUnavailable(
                f"worker could not find the command {command!r}: only commands relative to "
                f"{self.config.workdir} on the worker are routable (project files are not synced)"
            )
        return result


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
