"""Remote execution: hand a run to a bigger machine instead of faking it locally."""

from morph.cloud.capability import HostCapability, Shortfall, assess_locally
from morph.cloud.dispatch import NotReproducibleAnywhere, RunPlacement, run_anywhere
from morph.cloud.worker import RemoteWorker, WorkerUnavailable

__all__ = [
    "HostCapability",
    "NotReproducibleAnywhere",
    "RemoteWorker",
    "RunPlacement",
    "Shortfall",
    "WorkerUnavailable",
    "assess_locally",
    "run_anywhere",
]
