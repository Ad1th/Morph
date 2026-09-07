"""FastAPI route exposing the parameter metadata catalog.

The UI renders every parameter control from this metadata rather than
hardcoding widgets per field (docs/ui-spec.md section 6) -- so the frontend
fetches it from here instead of duplicating morph/schema/parameters.py.

Two entries in that catalog carry `max=None` with a comment saying the ceiling
is the host's: cores and memory. Served raw, "no maximum" reached the UI as no
maximum, and the slider fell back to an arbitrary 100 -- offering 100 cores on
a 16-core laptop, which is exactly the fake hardware equivalence the rest of
Morph refuses to do. This module resolves those two ceilings against hardware
that actually exists before the catalog leaves the process.

The ceiling is the larger of this host and the configured worker, not the host
alone: a profile that exceeds this machine is precisely what the cloud target
is for, so capping at local cores would make the worker unreachable from the UI.
"""

from __future__ import annotations

from fastapi import APIRouter

from morph.api.worker_probe import probe
from morph.schema.parameters import PARAMETER_CATALOG, ParameterMetadata

router = APIRouter()

def _host_capacity() -> tuple[int, int]:
    """This machine's PHYSICAL cores and total RAM in MB.

    Physical, because the ceiling being set is the one on cpu.cores, and the
    profiler fills that field from the physical count -- logical processors are
    a separate field. Bounding a physical-core slider by the logical count let
    this 8-core laptop offer 16, which is not a machine that exists.
    """
    from morph.cloud.capability import _host_cores, _host_memory_mb

    return _host_cores(), _host_memory_mb()


def _worker_capacity() -> tuple[int, int]:
    """The configured worker's cores and RAM, or (0, 0) if there isn't one.

    Fails soft on purpose. A worker that is configured but unreachable must not
    take the configuration screen down with it -- the ceiling just falls back to
    what this host can do, and the run itself still reports the real reason.
    """
    info = probe()
    if info is None or not info.reachable:
        return 0, 0
    return info.cores, info.memory_mb


@router.get("", response_model=dict[str, ParameterMetadata])
def get_parameter_catalog(target: str = "local") -> dict[str, ParameterMetadata]:
    """Return the catalog, with host-bounded maxima resolved to real hardware.

    `target` names the machine the run is headed for, and the ceilings describe
    THAT machine -- "local" this host, "cloud" the worker. A slider is a claim
    about what can be reproduced, so it has to describe one real computer: the
    union of the two describes neither, and would offer this laptop's 8 cores
    alongside the worker's 32 GB, a machine that exists nowhere.

    An unreachable worker falls back to this host's ceilings rather than to
    zero: a slider collapsed to its minimum reads as a broken screen, and the
    run itself still refuses, with the real reason.
    """
    host_cores, host_memory_mb = _host_capacity()
    worker_cores, worker_memory_mb = _worker_capacity()

    if target == "cloud" and worker_cores and worker_memory_mb:
        cores, memory_mb = worker_cores, worker_memory_mb
    else:
        cores, memory_mb = host_cores, host_memory_mb

    # Keyed by field_path, not by catalog key: the dotted path is the stable
    # identity of a parameter (it is where the value lands in the profile),
    # while the dict key is a label -- memory's is "ram_limit", which is easy
    # to guess wrong and fails silently by leaving the ceiling unresolved.
    ceilings = {
        "cpu.cores": float(cores),
        "memory.total_mb": float(memory_mb),
    }

    # Copies, never the catalog itself: PARAMETER_CATALOG is module-level state
    # shared by the CLI and the experiment engine, and editing it here would
    # pin one machine's hardware into every later consumer in the process.
    resolved: dict[str, ParameterMetadata] = {}
    for key, meta in PARAMETER_CATALOG.items():
        ceiling = ceilings.get(meta.field_path)
        if ceiling is not None and meta.max is None:
            resolved[key] = meta.model_copy(update={"max": ceiling})
        else:
            resolved[key] = meta
    return resolved
