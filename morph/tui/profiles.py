"""Small profile helpers shared by the TUI screens."""

from __future__ import annotations

from pathlib import Path

from morph.profiler.capture import capture_environment
from morph.schema.profile import EnvironmentProfile, FieldStatus, NetworkInfo, ProfileField

PROFILE_CANDIDATES = ("target_profile.json", "target.json", "profile.json")


def blank_network() -> NetworkInfo:
    return NetworkInfo(
        latency_ms=ProfileField(value=0.0, status=FieldStatus.REQUESTED),
        packet_loss_percent=ProfileField(value=0.0, status=FieldStatus.REQUESTED),
    )


def implicit_high_latency() -> EnvironmentProfile:
    """A sensible target when the user supplied none: this host, plus a
    latency + packet-loss network condition worth isolating."""
    profile = capture_environment()
    profile.network = profile.network or blank_network()
    profile.network.latency_ms = ProfileField(value=150.0, status=FieldStatus.REQUESTED)
    profile.network.packet_loss_percent = ProfileField(value=1.5, status=FieldStatus.REQUESTED)
    return profile


def resolve_profile(raw: str) -> EnvironmentProfile:
    """A path -> its EnvironmentProfile; blank / a hint string -> a discovered
    file in cwd, else the implicit high-latency target."""
    raw = (raw or "").strip()
    if not raw or raw.startswith("("):
        for name in PROFILE_CANDIDATES:
            if Path(name).is_file():
                raw = name
                break
    if raw and Path(raw).is_file():
        return EnvironmentProfile.model_validate_json(Path(raw).read_text(encoding="utf-8"))
    return implicit_high_latency()


def default_profile_hint() -> str:
    for name in PROFILE_CANDIDATES:
        if Path(name).is_file():
            return name
    return "(blank -> host + latency/loss)"
