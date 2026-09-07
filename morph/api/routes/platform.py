"""FastAPI route reporting where a run can actually execute.

Every capability flag comes from the active adapter's own `capabilities()`.
Nothing here invents a target: `remote-ssh` is listed so the UI can show it,
and reports `available: false` with the real reason until a worker host is
configured in morph.yaml / MORPH_CLOUD_HOST (docs/architecture.md: never fake
hardware equivalence).
"""

from __future__ import annotations

import platform as platform_mod

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

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
    capabilities: dict[str, bool] = Field(default_factory=dict)
    # Per-field fidelity the adapter predicts for a profile of this host with
    # a network section requested: {"network.latency_ms": {"status": ..., "mechanism": ..., "detail": ...}}.
    fidelity: dict[str, dict[str, str]] = Field(default_factory=dict)


class PlatformInfo(BaseModel):
    host: HostInfo
    targets: list[RunTarget]


def _remote_target() -> RunTarget:
    """The configured worker, if any. Configured is not the same as reachable;
    `morph doctor` / `morph cloud` probe it, this only reports the config."""
    try:
        from morph.cloud.worker import RemoteWorker
        from morph.config import load_config

        cfg = load_config()
        worker = RemoteWorker(getattr(cfg, "cloud", None) or getattr(cfg, "worker", None))
        configured = worker.configured
        target = worker.target if configured else None
    except Exception:
        configured, target = False, None
    return RunTarget(
        id="remote-ssh",
        family="linux",
        label=f"Remote Linux host ({target})" if target else "Remote Linux host (SSH)",
        available=configured,
        reason=None if configured else "No remote host configured",
        capabilities={},
    )


@router.get("", response_model=PlatformInfo, summary="Host OS and available run targets")
def get_platform() -> PlatformInfo:
    """Report the host OS and the run targets that are genuinely available."""
    from morph.profiler.collectors.os_info import collect_os
    from morph.runtime.controller import get_default_adapter

    try:
        os_info = collect_os()
        family = str(os_info.family.value)
        # On Windows the captured `version` is platform.release(), which is the
        # marketing release and reports "10" even on Windows 11. The build from
        # platform.version() ("10.0.26200") is the value that actually
        # identifies the host, so use it there. Elsewhere `version` is already
        # the distro/OS version, which beats a bare kernel number.
        version = os_info.kernel_version.value if family == "windows" else os_info.version.value
        host = HostInfo(family=family, version=str(version), arch=platform_mod.machine())
        adapter = get_default_adapter()
        capabilities = adapter.capabilities()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to inspect platform: {exc}") from exc

    fidelity: dict[str, dict[str, str]] = {}
    try:
        from morph.engine.runners import with_unconstrained_network
        from morph.profiler.capture import capture_environment
        from morph.runtime.controller import fidelity_report

        probe = with_unconstrained_network(capture_environment())
        probe.network.latency_ms.value = 1.0
        probe.network.packet_loss_percent.value = 1.0
        fidelity = {k: f.as_dict() for k, f in fidelity_report(probe, adapter).items()}
    except Exception:  # fidelity is advisory; capabilities remain the contract
        fidelity = {}

    local = RunTarget(
        id="local",
        family=family,
        label=f"This machine ({_FAMILY_LABELS.get(family, family)})",
        available=True,
        reason=None,
        capabilities=capabilities,
        fidelity=fidelity,
    )
    return PlatformInfo(host=host, targets=[local, _remote_target()])
