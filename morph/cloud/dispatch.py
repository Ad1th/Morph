"""Where should this run happen?

The rule, from PRD section 10 and section 25:

  * the profile fits this host          -> run here
  * it does not, and a worker can       -> run there
  * it does not, and no worker can      -> say so; never approximate silently

Cloud is a fallback, not a default (PRD section 25: "Do not run every
experiment in the cloud"). A run only leaves the machine when staying would
mean lying about the environment.
"""

from __future__ import annotations

from dataclasses import dataclass

from morph.cloud.capability import HostCapability, assess_locally
from morph.cloud.worker import RemoteWorker, WorkerUnavailable
from morph.runtime.controller import RuntimeController
from morph.schema.config import CloudConfig
from morph.schema.profile import EnvironmentProfile
from morph.schema.telemetry import RunResult


class NotReproducibleAnywhere(RuntimeError):
    """The host cannot satisfy the profile and no worker is available.

    Deliberately an error rather than a degraded run: PRD section 10 requires
    Morph either to reproduce the conditions, route somewhere that can, or
    refuse. Quietly running on a machine that does not match would produce
    evidence about the wrong environment.
    """

    def __init__(self, capability: HostCapability, reason: str) -> None:
        super().__init__(
            f"NOT_REPRODUCIBLE_LOCALLY: {capability.summary()}. {reason}"
        )
        self.capability = capability
        self.reason = reason


@dataclass
class RunPlacement:
    """Where a run went, and why."""

    location: str  # "local" | "cloud"
    capability: HostCapability
    worker_target: str | None = None

    @property
    def summary(self) -> str:
        if self.location == "local":
            return "ran on this host"
        return f"routed to {self.worker_target}: {self.capability.summary()}"


def run_anywhere(
    profile: EnvironmentProfile,
    command: str,
    timeout: float = 30.0,
    cloud: CloudConfig | None = None,
    controller: RuntimeController | None = None,
    worker: RemoteWorker | None = None,
    allow_cloud: bool = True,
    cwd: str | None = None,
) -> tuple[RunResult, RunPlacement]:
    """Run `command` under `profile` on whichever machine can honour it.

    Returns the result and where it ran. Raises NotReproducibleAnywhere when
    the profile exceeds this host and no worker can take it.

    `cwd` applies to a local run only: it is a path on THIS machine and would
    not exist on the worker, which uses its own configured checkout instead.
    """
    capability = assess_locally(profile)

    if capability.reproducible_locally:
        controller = controller or RuntimeController()
        result = controller.run(
            profile=profile, command=command, timeout=timeout, cwd=cwd
        )
        return result, RunPlacement(location="local", capability=capability)

    if not allow_cloud:
        raise NotReproducibleAnywhere(
            capability, "Cloud routing was not permitted for this run."
        )

    worker = worker or RemoteWorker(cloud)
    if not worker.configured:
        raise NotReproducibleAnywhere(
            capability,
            "No worker is configured. Set cloud.host in morph.yaml, "
            "or MORPH_CLOUD_HOST in the environment.",
        )

    try:
        result = worker.run(profile=profile, command=command, timeout=timeout)
    except WorkerUnavailable as exc:
        raise NotReproducibleAnywhere(capability, f"The worker could not run it: {exc}") from exc

    return result, RunPlacement(
        location="cloud", capability=capability, worker_target=worker.target
    )
