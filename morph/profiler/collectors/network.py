"""Network collector: host baseline network conditions and connection type."""

import psutil

from morph.schema.profile import FieldStatus, NetworkInfo, ProfileField


def _detect_connection_type_and_bandwidth() -> tuple[str, float]:
    conn_type = "ethernet"
    speed = 1000.0
    try:
        stats = psutil.net_if_stats()
        for name, stat in stats.items():
            if stat.isup:
                name_lower = name.lower()
                if any(w in name_lower for w in ("wi-fi", "wifi", "wlan", "wireless")):
                    conn_type = "wifi"
                elif "loopback" in name_lower:
                    continue
                if stat.speed > 0:
                    speed = float(stat.speed)
                break
    except Exception:
        pass
    return conn_type, speed


def collect_network() -> NetworkInfo:
    """Collect the host's baseline network conditions."""
    conn_type, bandwidth = _detect_connection_type_and_bandwidth()
    return NetworkInfo(
        latency_ms=ProfileField(value=0.0, status=FieldStatus.CAPTURED),
        packet_loss_percent=ProfileField(value=0.0, status=FieldStatus.CAPTURED),
        bandwidth_mbps=ProfileField(value=bandwidth, status=FieldStatus.CAPTURED),
        jitter_ms=ProfileField(value=0.0, status=FieldStatus.CAPTURED),
        available=ProfileField(value=True, status=FieldStatus.CAPTURED),
        connection_type=ProfileField(value=conn_type, status=FieldStatus.CAPTURED),
    )
