"""Small profile helpers shared by the TUI screens."""

from __future__ import annotations

from pathlib import Path

from morph.profiler.capture import capture_environment
from morph.schema.profile import EnvironmentProfile, FieldStatus, NetworkInfo, ProfileField

PROFILE_CANDIDATES = ("target_profile.json", "target.json", "profile.json")
BLANK_HINT = "(blank → host + latency/loss)"

# Parameters the Monitor / Threshold / matrix all agree on:
# dotted path -> (label, unit, direction, low, high, step, big_step, fmt)
PARAMS: dict[str, dict] = {
    "network.latency_ms": {
        "label": "latency", "unit": "ms", "direction": "up",
        "low": 0.0, "high": 400.0, "step": 5.0, "big_step": 50.0, "fmt": ".0f",
    },
    "network.packet_loss_percent": {
        "label": "loss", "unit": "%", "direction": "up",
        "low": 0.0, "high": 20.0, "step": 0.5, "big_step": 5.0, "fmt": ".1f",
    },
    "cpu.cores": {
        "label": "cpu cores", "unit": "", "direction": "down",
        "low": 1.0, "high": 8.0, "step": 1.0, "big_step": 2.0, "fmt": ".0f",
    },
    "memory.total_mb": {
        "label": "ram", "unit": " MB", "direction": "down",
        "low": 256.0, "high": 16384.0, "step": 256.0, "big_step": 2048.0, "fmt": ".0f",
    },
}


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


def fidelity_badges(profile: EnvironmentProfile, adapter=None) -> dict[str, tuple[str, str]]:
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

    report = None
    fn = getattr(adapter, "fidelity", None)
    if callable(fn):
        try:
            report = fn()
        except Exception:
            report = None
    if isinstance(report, dict):
        for param in PARAMS:
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

    if len(badges) < len(PARAMS):
        reconciled = reconcile_profile_statuses(profile, adapter)
        for param in PARAMS:
            if param in badges:
                continue
            fld = _dotted(reconciled, param)
            status = getattr(fld, "status", None)
            if status is not None:
                badges[param] = (str(getattr(status, "value", status)).lower(), "")
    return badges
