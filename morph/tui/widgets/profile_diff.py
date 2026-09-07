"""ProfileDiff -- an EnvironmentProfile as a field / value / status table.

After a reconcile pass each row's status badge reads REPRODUCED (this host can
do it), APPROXIMATED (close enough), or UNAVAILABLE (it cannot) -- the single
most legible view of what "reproducing an environment" actually delivers.
"""

from __future__ import annotations

from rich.text import Text
from textual.widgets import DataTable

from morph.schema.profile import EnvironmentProfile, FieldStatus
from morph.tui.theme import palette, status_style

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

_STATUS_TEXT = {
    FieldStatus.REPRODUCED: "REPRODUCED",
    FieldStatus.APPROXIMATED: "APPROXIMATED",
    FieldStatus.UNAVAILABLE: "UNAVAILABLE",
    FieldStatus.CAPTURED: "captured",
    FieldStatus.REQUESTED: "requested",
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
            self.add_row(label, "-", "-", key=path)
        self.border_title = "TARGET PROFILE"

    def show(self, profile: EnvironmentProfile, notes: dict[str, str] | None = None) -> None:
        p = palette(self)
        for _label, path in _ROWS:
            fld = _field(profile, path)
            if fld is None:
                value_cell = Text("n/a", style=p.muted)
                status_cell = Text("-", style=p.muted)
            else:
                editable = path in EDITABLE
                value_cell = Text(str(fld.value), style=f"bold {p.text}" if editable else p.muted)
                text = _STATUS_TEXT.get(fld.status, str(fld.status))
                status_cell = Text(text, style=status_style(p, str(getattr(fld.status, "value", fld.status))))
                note = (notes or {}).get(path)
                if note:
                    status_cell.append(f"  {note}", style=p.muted)
            self.update_cell(path, self._col_value, value_cell, update_width=True)
            self.update_cell(path, self._col_status, status_cell, update_width=True)

    def path_at_cursor(self) -> str | None:
        try:
            row_key, _col = self.coordinate_to_cell_key(self.cursor_coordinate)
        except Exception:
            return None
        return row_key.value
