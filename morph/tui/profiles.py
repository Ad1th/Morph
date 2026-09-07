"""Small profile helpers shared by the TUI screens."""

from __future__ import annotations

from pathlib import Path

from morph.profiler.capture import capture_environment
from morph.schema.profile import EnvironmentProfile, FieldStatus, NetworkInfo, ProfileField

PROFILE_CANDIDATES = ("target_profile.json", "target.json", "profile.json")
BLANK_HINT = "(blank → host + latency/loss)"

# The four continuous parameters the Threshold / matrix screens sweep:
# dotted path -> (label, unit, direction, low, high, step, big_step, fmt)
PARAMS: dict[str, dict] = {
    "network.latency_ms": {
        "label": "latency",
        "unit": "ms",
        "direction": "up",
        "low": 0.0,
        "high": 400.0,
        "step": 5.0,
        "big_step": 50.0,
        "fmt": ".0f",
    },
    "network.packet_loss_percent": {
        "label": "loss",
        "unit": "%",
        "direction": "up",
        "low": 0.0,
        "high": 20.0,
        "step": 0.5,
        "big_step": 5.0,
        "fmt": ".1f",
    },
    "cpu.cores": {
        "label": "cpu cores",
        "unit": "",
        "direction": "down",
        "low": 1.0,
        "high": 8.0,
        "step": 1.0,
        "big_step": 2.0,
        "fmt": ".0f",
    },
    "memory.total_mb": {
        "label": "ram",
        "unit": " MB",
        "direction": "down",
        "low": 256.0,
        "high": 16384.0,
        "step": 256.0,
        "big_step": 2048.0,
        "fmt": ".0f",
    },
}


# Everything the Monitor exposes, grouped the way the dashboard groups them.
# kind: "range" (slider) | "choice" (cycle through labels) | "toggle" (on/off).
# For choices/toggles the slider's numeric value is an index into `choices`.
def _rng(label, unit, direction, low, high, step, big_step, fmt, group):
    return {
        "kind": "range",
        "label": label,
        "unit": unit,
        "direction": direction,
        "low": low,
        "high": high,
        "step": step,
        "big_step": big_step,
        "fmt": fmt,
        "group": group,
    }


def _choice(label, choices, group, default=0):
    return {
        "kind": "choice",
        "label": label,
        "unit": "",
        "direction": "up",
        "low": 0.0,
        "high": float(len(choices) - 1),
        "step": 1.0,
        "big_step": 1.0,
        "fmt": ".0f",
        "group": group,
        "choices": list(choices),
        "default": default,
    }


def _toggle(label, group, default=True):
    return {**_choice(label, ["off", "on"], group, default=1 if default else 0), "kind": "toggle"}


ALL_PARAMS: dict[str, dict] = {
    # --- network ---
    "network.available": _toggle("network", "network"),
    "network.connection_type": _choice(
        "connection", ["ethernet", "wifi", "cellular", "vpn", "satellite"], "network"
    ),
    "network.latency_ms": {**PARAMS["network.latency_ms"], "kind": "range", "group": "network"},
    "network.packet_loss_percent": {
        **PARAMS["network.packet_loss_percent"],
        "kind": "range",
        "group": "network",
    },
    "network.bandwidth_mbps": _rng("bandwidth", " Mb/s", "down", 0.5, 1000.0, 0.5, 50.0, ".1f", "network"),
    "network.jitter_ms": _rng("jitter", " ms", "up", 0.0, 200.0, 2.0, 20.0, ".0f", "network"),
    # --- cpu and memory ---
    "cpu.cores": {**PARAMS["cpu.cores"], "kind": "range", "group": "cpu and memory"},
    "cpu.quota_percent": _rng("cpu quota", " %", "down", 5.0, 100.0, 5.0, 25.0, ".0f", "cpu and memory"),
    "memory.total_mb": {**PARAMS["memory.total_mb"], "kind": "range", "group": "cpu and memory"},
    "memory.pressure_percent": _rng(
        "ram pressure", " %", "up", 0.0, 90.0, 5.0, 25.0, ".0f", "cpu and memory"
    ),
    "memory.swap_mb": _rng("swap", " MB", "down", 0.0, 8192.0, 256.0, 2048.0, ".0f", "cpu and memory"),
    "cpu.architecture": _choice("arch", ["x86_64", "arm64", "aarch64", "riscv64"], "cpu and memory"),
    "os.family": _choice("os", ["darwin", "linux", "windows"], "cpu and memory"),
    # --- locale and time ---
    "locale.locale": _choice(
        "locale",
        ["en_US.UTF-8", "en_IN.UTF-8", "de_DE.UTF-8", "fr_FR.UTF-8", "ja_JP.UTF-8", "C"],
        "locale and time",
    ),
    "locale.timezone": _choice(
        "timezone",
        ["UTC", "Asia/Kolkata", "America/New_York", "Europe/Berlin", "America/Sao_Paulo", "Asia/Tokyo"],
        "locale and time",
    ),
    # --- filesystem ---
    "filesystem.case_sensitive": _toggle("case-sens.", "filesystem"),
    "filesystem.read_only": _toggle("read-only", "filesystem", default=False),
    "filesystem.disk_space_limit_mb": _rng(
        "disk space", " MB", "down", 64.0, 65536.0, 64.0, 4096.0, ".0f", "filesystem"
    ),
    "filesystem.disk_read_latency_ms": _rng(
        "disk read", " ms", "up", 0.0, 100.0, 1.0, 10.0, ".0f", "filesystem"
    ),
    "filesystem.disk_write_latency_ms": _rng(
        "disk write", " ms", "up", 0.0, 100.0, 1.0, 10.0, ".0f", "filesystem"
    ),
    # --- process and runtime ---
    "process.timeout_s": _rng("timeout", " s", "down", 0.5, 60.0, 0.5, 5.0, ".1f", "process"),
    "process.max_processes": _rng("processes", "", "down", 1.0, 512.0, 1.0, 32.0, ".0f", "process"),
    "process.thread_limit": _rng("threads", "", "down", 1.0, 1024.0, 1.0, 64.0, ".0f", "process"),
    "process.fd_limit": _rng("open files", "", "down", 8.0, 4096.0, 8.0, 256.0, ".0f", "process"),
}

PARAM_GROUPS: list[str] = ["network", "cpu and memory", "locale and time", "filesystem", "process"]


def param_value(param: str, raw: float) -> float | str | bool:
    """The value to put in the profile for a slider reading: the number for a
    range, the label for a choice, True/False for a toggle."""
    spec = ALL_PARAMS.get(param)
    if not spec or spec.get("kind") == "range":
        return raw
    idx = max(0, min(len(spec["choices"]) - 1, round(raw)))
    if spec["kind"] == "toggle":
        return idx == 1
    return spec["choices"][idx]


def param_text(param: str, raw: float) -> str:
    """Human reading of a slider value, for warnings and logs."""
    spec = ALL_PARAMS.get(param)
    if not spec or spec.get("kind") == "range":
        return f"{raw:{(spec or {}).get('fmt', 'g')}}{(spec or {}).get('unit', '')}".strip()
    return str(param_value(param, raw))


def blank_network() -> NetworkInfo:
    return NetworkInfo(
        latency_ms=ProfileField(value=0.0, status=FieldStatus.REQUESTED),
        packet_loss_percent=ProfileField(value=0.0, status=FieldStatus.REQUESTED),
    )


def implicit_high_latency(host: EnvironmentProfile | None = None) -> EnvironmentProfile:
    """A sensible target when the user supplied none: this host, plus a
    latency + packet-loss network condition worth isolating."""
    profile = host.model_copy(deep=True) if host is not None else capture_environment()
    profile.network = profile.network or blank_network()
    profile.network.latency_ms = ProfileField(value=150.0, status=FieldStatus.REQUESTED)
    profile.network.packet_loss_percent = ProfileField(value=1.5, status=FieldStatus.REQUESTED)
    return profile


def resolve_profile(raw: str) -> EnvironmentProfile:
    """A path -> its EnvironmentProfile. Blank (or the placeholder hint) -> a
    discovered ``target_profile.json`` in cwd, else the implicit high-latency
    target. A non-blank path that does not exist is an error, never a silent
    substitution (a typo must not run a different experiment)."""
    raw = (raw or "").strip()
    if not raw or raw.startswith("("):
        for name in PROFILE_CANDIDATES:
            if Path(name).is_file():
                raw = name
                break
        else:
            return implicit_high_latency()
    path = Path(raw)
    if not path.is_file():
        raise FileNotFoundError(f"profile not found: {raw}")
    return EnvironmentProfile.model_validate_json(path.read_text(encoding="utf-8"))


def default_profile_hint() -> str:
    for name in PROFILE_CANDIDATES:
        if Path(name).is_file():
            return name
    return BLANK_HINT


def _dotted(obj: object, dotted: str) -> object | None:
    for part in dotted.split("."):
        obj = getattr(obj, part, None)
        if obj is None:
            return None
    return obj


def fidelity_badges(
    profile: EnvironmentProfile, adapter=None, params: dict | None = None
) -> dict[str, tuple[str, str]]:
    """Per-parameter ``(status, note)`` badges for the current host.

    Reads the adapter's fidelity report (``BaseAdapter.fidelity()``: dotted
    field path -> ``Fidelity(status, mechanism, detail)``) and falls back to
    :func:`reconcile_profile_statuses` for anything it does not cover. Status
    strings are FieldStatus values (``reproduced`` / ``approximated`` /
    ``unavailable``); the note is the mechanism the adapter would use.
    """
    from morph.runtime.controller import get_default_adapter, reconcile_profile_statuses

    adapter = adapter or get_default_adapter()
    badges: dict[str, tuple[str, str]] = {}
    params = params or PARAMS

    report = None
    fn = getattr(adapter, "fidelity", None)
    if callable(fn):
        try:
            report = fn()
        except Exception:
            report = None
    if isinstance(report, dict):
        for param in params:
            entry = report.get(param)
            if entry is None:
                continue
            status = getattr(entry, "status", None)
            if status is None and isinstance(entry, dict):
                status = entry.get("status")
            if status is None:
                continue
            mechanism = getattr(entry, "mechanism", None)
            if mechanism is None and isinstance(entry, dict):
                mechanism = entry.get("mechanism", "")
            mechanism = str(mechanism or "")
            note = "" if mechanism in ("", "capability") else mechanism
            badges[param] = (str(getattr(status, "value", status)).lower(), note)

    if len(badges) < len(params):
        reconciled = reconcile_profile_statuses(profile, adapter)
        for param in params:
            if param in badges:
                continue
            fld = _dotted(reconciled, param)
            status = getattr(fld, "status", None)
            if status is not None:
                badges[param] = (str(getattr(status, "value", status)).lower(), "")
    return badges
