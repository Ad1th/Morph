"""Parameter metadata catalog (docs/ui-spec.md section 6).

The UI renders parameter controls entirely from this metadata rather than
hardcoding widgets per field: "adding a parameter later is a metadata entry,
not new UI code" (ui-spec.md section 6). This module is that metadata's
backend source of truth, scoped to the MVP catalog (ui-spec.md section 2).

Phase 2 parameters (jitter, CPU quota, swap, disk latency, ...) are
deliberately NOT included here: several of them (jitter, CPU quota) have no
corresponding EnvironmentProfile field yet, and the rest depend on runtime
adapters that don't exist. Per the spec's own closing line: "Phase-2
parameters get their controls only once their runtime adapters exist."
"""

from __future__ import annotations

from pydantic import BaseModel


class ParameterMetadata(BaseModel):
    name: str
    field_path: str  # dotted path into EnvironmentProfile, e.g. "cpu.cores"
    unit: str
    min: float | None = None
    max: float | None = None
    default: float | str | None = None
    step: float | None = None
    detectable: bool = True
    controllable: bool = True
    experimentable: bool = False
    platform_support: dict[str, str] = {}  # os family -> badge ("local"|"approx"|"worker"|"unsupported")


MVP_PARAMETERS: dict[str, ParameterMetadata] = {
    "cpu_cores": ParameterMetadata(
        name="CPU cores",
        field_path="cpu.cores",
        unit="count",
        min=1,
        max=None,  # host logical CPUs; resolved against a captured host profile
        step=1,
        experimentable=True,
        platform_support={"windows": "local", "darwin": "local", "linux": "local"},
    ),
    "ram_limit": ParameterMetadata(
        name="RAM limit",
        field_path="memory.total_mb",
        unit="MiB",
        min=256,
        max=None,  # host RAM
        experimentable=True,
        platform_support={"windows": "local", "darwin": "unsupported", "linux": "local"},
    ),
    "network_latency": ParameterMetadata(
        name="Network latency",
        field_path="network.latency_ms",
        unit="ms",
        min=0,
        max=5000,
        default=0,
        experimentable=True,
        platform_support={"windows": "local", "darwin": "local", "linux": "local"},
    ),
    "packet_loss": ParameterMetadata(
        name="Packet loss",
        field_path="network.packet_loss_percent",
        unit="%",
        min=0,
        max=30,
        default=0,
        experimentable=True,
        platform_support={"windows": "local", "darwin": "local", "linux": "local"},
    ),
    "bandwidth": ParameterMetadata(
        name="Bandwidth",
        field_path="network.bandwidth_mbps",
        unit="Mbit/s",
        min=0.1,
        max=1000,
        default="Unlimited",
        detectable=False,
        experimentable=True,
        platform_support={"windows": "approx", "darwin": "approx", "linux": "local"},
    ),
    "locale": ParameterMetadata(
        name="Locale",
        field_path="locale.locale",
        unit="BCP-47",
        controllable=True,
        platform_support={"windows": "local", "darwin": "local", "linux": "local"},
    ),
    "timezone": ParameterMetadata(
        name="Timezone",
        field_path="locale.timezone",
        unit="IANA name",
        controllable=True,
        platform_support={"windows": "local", "darwin": "local", "linux": "local"},
    ),
}
