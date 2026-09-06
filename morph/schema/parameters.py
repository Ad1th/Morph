"""Parameter metadata catalog (docs/ui-spec.md sections 2, 3, and 6).

The UI renders parameter controls entirely from this metadata rather than
hardcoding widgets per field: "adding a parameter later is a metadata entry,
not new UI code" (ui-spec.md section 6). This module is that metadata's
backend source of truth.

MVP_PARAMETERS covers section 2 exactly (including cpu_quota and jitter,
which an earlier pass here incorrectly filed as "Phase 2" because their
schema fields didn't exist yet -- they do now, see morph/schema/profile.py).
PHASE2_PARAMETERS covers section 3, minus three that are cut entirely rather
than given a permanently-unsupported metadata entry: system time override,
clock offset, and time speed. All three need libfaketime (POSIX-only, not
installed, LD_PRELOAD-based) or admin-level clock control with no
cross-platform equivalent -- there is no path to ever supporting them on
this stack, so they're left out rather than rendered as a row that can never
work (docs/architecture.md section 16: "never fake hardware equivalence").

Environment variables (a key-value row editor, not a slider/toggle/dropdown)
don't fit this per-field min/max/default shape and aren't listed here;
EnvironmentProfile.env_vars is a plain dict handled directly by the API/UI.
"""

from __future__ import annotations

from pydantic import BaseModel


class ParameterMetadata(BaseModel):
    name: str
    field_path: str  # dotted path into EnvironmentProfile, e.g. "cpu.cores"
    unit: str
    min: float | None = None
    max: float | None = None
    default: bool | float | str | None = None  # bool before float: True/False must not coerce to 1.0/0.0
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
    "cpu_quota": ParameterMetadata(
        name="CPU quota",
        field_path="cpu.quota_percent",
        unit="%",
        min=1,
        max=None,  # cores * 100; resolved against the profile's own cpu.cores
        default=None,  # unthrottled
        step=1,
        experimentable=True,
        platform_support={"windows": "approx", "darwin": "approx", "linux": "local"},
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
    "jitter": ParameterMetadata(
        name="Jitter",
        field_path="network.jitter_ms",
        unit="ms",
        min=0,
        max=500,  # and <= current latency -- cross-field rule, see engine/validator.py
        default=0,
        experimentable=True,
        platform_support={"windows": "local", "darwin": "local", "linux": "local"},
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


PHASE2_PARAMETERS: dict[str, ParameterMetadata] = {
    "memory_pressure": ParameterMetadata(
        name="Memory pressure",
        field_path="memory.pressure_percent",
        unit="% of limit pre-consumed",
        min=0,
        max=95,
        default=0,
        step=5,
        detectable=False,  # not a host fact -- a control applied before the app starts
        # Real balloon allocation needs a helper process holding the memory for
        # the run's lifetime; not wired to any adapter yet, so this stays
        # display-only rather than a control that silently does nothing.
        controllable=False,
        platform_support={"windows": "unsupported", "darwin": "unsupported", "linux": "unsupported"},
    ),
    "swap": ParameterMetadata(
        name="Swap",
        field_path="memory.swap_mb",
        unit="MiB",
        min=0,
        max=8192,
        default=0,
        step=256,
        # Detectable (real host swap total via psutil), but resizing swap
        # needs root on every platform -- detection only, no fake control.
        controllable=False,
        platform_support={"windows": "unsupported", "darwin": "unsupported", "linux": "unsupported"},
    ),
    "cpu_architecture": ParameterMetadata(
        name="CPU architecture",
        field_path="cpu.architecture",
        unit="",
        controllable=False,  # worker selector, not a local control
        platform_support={"windows": "worker", "darwin": "worker", "linux": "worker"},
    ),
    "os": ParameterMetadata(
        name="OS",
        field_path="os.family",
        unit="",
        controllable=False,
        platform_support={"windows": "worker", "darwin": "worker", "linux": "worker"},
    ),
    "os_version": ParameterMetadata(
        name="OS version",
        field_path="os.version",
        unit="",
        controllable=False,
        platform_support={"windows": "worker", "darwin": "worker", "linux": "worker"},
    ),
    "kernel_version": ParameterMetadata(
        name="Kernel version",
        field_path="os.kernel_version",
        unit="",
        controllable=False,
        platform_support={"windows": "worker", "darwin": "worker", "linux": "worker"},
    ),
    "filesystem_type": ParameterMetadata(
        name="Filesystem type",
        field_path="filesystem.filesystem_type",
        unit="",
        controllable=False,  # loopback-image or worker, per ui-spec.md section 3
        platform_support={"windows": "worker", "darwin": "worker", "linux": "worker"},
    ),
    "disk_space_limit": ParameterMetadata(
        name="Disk space limit",
        field_path="filesystem.disk_space_limit_mb",
        unit="MiB",
        min=100,
        max=None,  # host free space
        controllable=False,  # real enforcement needs a loopback image/quota
        platform_support={"windows": "unsupported", "darwin": "unsupported", "linux": "unsupported"},
    ),
    "disk_read_latency": ParameterMetadata(
        name="Disk read latency",
        field_path="filesystem.disk_read_latency_ms",
        unit="ms/op",
        min=0,
        max=100,
        default=0,
        step=0.5,
        detectable=False,
        controllable=False,
        platform_support={"windows": "unsupported", "darwin": "unsupported", "linux": "unsupported"},
    ),
    "disk_write_latency": ParameterMetadata(
        name="Disk write latency",
        field_path="filesystem.disk_write_latency_ms",
        unit="ms/op",
        min=0,
        max=100,
        default=0,
        step=0.5,
        detectable=False,
        controllable=False,
        platform_support={"windows": "unsupported", "darwin": "unsupported", "linux": "unsupported"},
    ),
    "read_only_filesystem": ParameterMetadata(
        name="Read-only filesystem",
        field_path="filesystem.read_only",
        unit="",
        default=False,
        detectable=False,
        controllable=False,  # not wired to the runtime controller yet
        platform_support={"windows": "unsupported", "darwin": "unsupported", "linux": "unsupported"},
    ),
    "case_sensitivity": ParameterMetadata(
        name="Case sensitivity",
        field_path="filesystem.case_sensitive",
        unit="",
        controllable=False,  # needs a case-toggled FS image or a worker
        # "approx" everywhere: ext4 on Linux is case-sensitive by default, so
        # a request matching that default happens to hold, but there is no
        # toggle -- it is never genuinely *controlled*, just sometimes true.
        platform_support={"windows": "worker", "darwin": "worker", "linux": "approx"},
    ),
    "process_timeout": ParameterMetadata(
        name="Process timeout",
        field_path="process.timeout_s",
        unit="s",
        min=1,
        max=3600,
        default=None,  # off
        step=1,
        detectable=False,
        platform_support={"windows": "local", "darwin": "local", "linux": "local"},
    ),
    "max_processes": ParameterMetadata(
        name="Max processes",
        field_path="process.max_processes",
        unit="count",
        min=1,
        max=4096,
        step=1,
        platform_support={"windows": "unsupported", "darwin": "local", "linux": "local"},
    ),
    "thread_limit": ParameterMetadata(
        name="Thread limit",
        field_path="process.thread_limit",
        unit="count",
        min=1,
        max=10000,
        step=1,
        detectable=False,  # no distinct rlimit from max_processes on POSIX
        controllable=False,
        platform_support={"windows": "unsupported", "darwin": "unsupported", "linux": "unsupported"},
    ),
    "fd_limit": ParameterMetadata(
        name="File descriptor limit",
        field_path="process.fd_limit",
        unit="count",
        min=64,
        max=1048576,
        step=1024,
        platform_support={"windows": "unsupported", "darwin": "local", "linux": "local"},
    ),
    "network_availability": ParameterMetadata(
        name="Network availability",
        field_path="network.available",
        unit="",
        default=True,  # online
        detectable=False,
        platform_support={"windows": "local", "darwin": "local", "linux": "local"},
    ),
    "connection_type": ParameterMetadata(
        name="Connection type",
        field_path="network.connection_type",
        unit="",
        detectable=False,
        # Writes the four network sliders (docs/ui-spec.md section 4); not an
        # independently applied condition itself.
        controllable=True,
        platform_support={"windows": "local", "darwin": "local", "linux": "local"},
    ),
}


PARAMETER_CATALOG: dict[str, ParameterMetadata] = {**MVP_PARAMETERS, **PHASE2_PARAMETERS}
