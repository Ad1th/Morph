"""ProfileDiff -- an EnvironmentProfile as a field / value / status table.

After a reconcile pass each row's status badge reads REPRODUCED (this host can
do it), APPROXIMATED (close enough), or UNAVAILABLE (it cannot) -- the single
most legible view of what "reproducing an environment" actually delivers.
"""

from __future__ import annotations

from rich.text import Text
from textual.widgets import DataTable

from morph.schema.profile import EnvironmentProfile, FieldStatus

# (row label, dotted path) in display order
_ROWS: list[tuple[str, str]] = [
    ("OS family", "os.family"),
    ("OS version", "os.version"),
    ("CPU arch", "cpu.architecture"),
    ("CPU cores", "cpu.cores"),
    ("RAM (MB)", "memory.total_mb"),
    ("locale", "locale.locale"),
    ("timezone", "locale.timezone"),
    ("net latency (ms)", "network.latency_ms"),
    ("net loss (%)", "network.packet_loss_percent"),
]

_STATUS_STYLE = {
    FieldStatus.REPRODUCED: ("REPRODUCED", "bold green"),
    FieldStatus.APPROXIMATED: ("APPROXIMATED", "bold yellow"),
    FieldStatus.UNAVAILABLE: ("UNAVAILABLE", "bold red3"),
    FieldStatus.CAPTURED: ("captured", "dim"),
    FieldStatus.REQUESTED: ("requested", "dim cyan"),
}

# dotted paths safe to edit inline
EDITABLE = {
    "cpu.cores",
    "memory.total_mb",
    "network.latency_ms",
    "network.packet_loss_percent",
}


def _field(profile: EnvironmentProfile, dotted: str):
    section: object = profile
    parts = dotted.split(".")
    for part in parts[:-1]:
        section = getattr(section, part, None)
        if section is None:
            return None
    return getattr(section, parts[-1], None)


class ProfileDiff(DataTable):
    def on_mount(self) -> None:
        self.cursor_type = "row"
        self.zebra_stripes = True
        keys = self.add_columns("field", "target value", "status")
        self._col_value = keys[1]
        self._col_status = keys[2]
        for label, path in _ROWS:
            self.add_row(label, "—", "—", key=path)

    def show(self, profile: EnvironmentProfile) -> None:
        for _label, path in _ROWS:
            fld = _field(profile, path)
            if fld is None:
                value_cell = Text("n/a", style="grey37")
                status_cell = Text("—", style="grey37")
            else:
                editable = path in EDITABLE
                value_cell = Text(str(fld.value), style="white" if editable else "grey70")
                text, style = _STATUS_STYLE.get(fld.status, (str(fld.status), "dim"))
                status_cell = Text(text, style=style)
            self.update_cell(path, self._col_value, value_cell)
            self.update_cell(path, self._col_status, status_cell)

    def path_at_cursor(self) -> str | None:
        try:
            row_key, _col = self.coordinate_to_cell_key(self.cursor_coordinate)
        except Exception:
            return None
        return row_key.value
