"""FastAPI route reporting where a run can actually execute.

Every capability flag comes from the active adapter's own `capabilities()`.
Nothing here invents a target: `remote-ssh` is listed so the UI can show it,
but it reports `available: false` with the real reason until a remote host is
configured (docs/architecture.md: never fake hardware equivalence).
"""

from __future__ import annotations

import platform as platform_mod

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from morph.profiler.collectors.os_info import collect_os
from morph.runtime.controller import get_default_adapter

router = APIRouter()

_FAMILY_LABELS = {"windows": "Windows", "darwin": "macOS", "linux": "Linux"}


class HostInfo(BaseModel):
    family: str
    version: str
    arch: str


class RunTarget(BaseModel):
    id: str
    family: str
    label: str
    available: bool
    reason: str | None = None
    capabilities: dict[str, bool] = {}


class PlatformInfo(BaseModel):
    host: HostInfo
    targets: list[RunTarget]


@router.get("", response_model=PlatformInfo)
def get_platform() -> PlatformInfo:
    """Report the host OS and the run targets that are genuinely available."""
    try:
        os_info = collect_os()
        family = str(os_info.family.value)
        # On Windows the captured `version` is platform.release(), which is the
        # marketing release and reports "10" even on Windows 11. The build from
        # platform.version() ("10.0.26200") is the value that actually
        # identifies the host, so use it there. Elsewhere `version` is already
        # the distro/OS version, which beats a bare kernel number.
        version = os_info.kernel_version.value if family == "windows" else os_info.version.value
        host = HostInfo(
            family=family,
            version=str(version),
            arch=platform_mod.machine(),
        )
        capabilities = get_default_adapter().capabilities()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to inspect platform: {exc}")

    local = RunTarget(
        id="local",
        family=family,
        label=f"This machine ({_FAMILY_LABELS.get(family, family)})",
        available=True,
        reason=None,
        capabilities=capabilities,
    )
    remote = RunTarget(
        id="remote-ssh",
        family="linux",
        label="Remote Linux host (SSH)",
        available=False,
        reason="No remote host configured",
        capabilities={},
    )
    return PlatformInfo(host=host, targets=[local, remote, _cloud_target()])


def _cloud_target() -> RunTarget:
    """The configured cloud worker, described by what it actually reports.

    Deliberately probes rather than trusting morph.yaml. A config file says a
    worker was intended; only the probe says one is there, and the difference
    between those two shows up mid-demo if the UI offers a target that cannot
    take the run. An unreachable worker is still listed -- with the reason the
    probe gave -- because "configured but down" is a fixable state the user
    needs to see, and hiding the row would just look like the feature is gone.
    """
    unconfigured = RunTarget(
        id="cloud",
        family="linux",
        label="Cloud worker",
        available=False,
        reason="No cloud worker configured. Set cloud.host in morph.yaml, "
        "or MORPH_CLOUD_HOST in the environment.",
        capabilities={},
    )
    try:
        from morph.api.worker_probe import probe
        from morph.cloud.worker import RemoteWorker
        from morph.config import load_config

        info = probe()
        if info is None:
            return unconfigured

        worker = RemoteWorker(load_config().cloud)
        if not info.usable:
            return RunTarget(
                id="cloud",
                family="linux",
                label=f"Cloud worker ({worker.target})",
                available=False,
                reason=info.detail or "worker is not reachable",
                capabilities={},
            )

        # Both numbers, because they differ on a cloud VM and the difference is
        # the kind of thing that derails a demo question: a GCP vCPU is a
        # hyperthread, so this 8-vCPU box has 4 physical cores.
        specs = (
            f"{info.cores} cores / {info.logical} vCPU, {info.memory_mb // 1024} GB"
            if info.cores
            else "reachable"
        )
        return RunTarget(
            id="cloud",
            family="linux",
            label=f"Cloud worker -- {worker.target} ({specs})",
            available=True,
            reason=None,
            # The worker shapes the network with real `tc`, which is the whole
            # reason to prefer it over this host for network experiments.
            capabilities={"network_shaping": info.can_shape_network},
        )
    except Exception as exc:
        return RunTarget(
            id="cloud",
            family="linux",
            label="Cloud worker",
            available=False,
            reason=f"Could not probe the worker: {exc}",
            capabilities={},
        )
