"""Environment screen -- capture the host, shape a target profile, and see it
reconciled field-by-field (REPRODUCED / APPROXIMATED / UNAVAILABLE).
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import Button, Footer, Input, Select, Static

from morph.profiler.capture import capture_environment
from morph.runtime.controller import reconcile_profile_statuses
from morph.schema.profile import EnvironmentProfile, FieldStatus, NetworkInfo, ProfileField
from morph.tui.messages import RunFinished
from morph.tui.orchestrator import set_profile_parameter
from morph.tui.widgets.profile_diff import EDITABLE, ProfileDiff

_TEMPLATES = ("host (as captured)", "high-latency", "constrained", "raspberry-pi-ish")


def _ensure_network(profile: EnvironmentProfile) -> None:
    if profile.network is None:
        profile.network = NetworkInfo(
            latency_ms=ProfileField(value=0.0, status=FieldStatus.REQUESTED),
            packet_loss_percent=ProfileField(value=0.0, status=FieldStatus.REQUESTED),
        )


def apply_template(profile: EnvironmentProfile, template: str) -> EnvironmentProfile:
    """Shape a captured host profile into a named target."""
    out = profile.model_copy(deep=True)
    _ensure_network(out)
    if template == "high-latency":
        out.network.latency_ms = ProfileField(value=180.0, status=FieldStatus.REQUESTED)
        out.network.packet_loss_percent = ProfileField(value=2.0, status=FieldStatus.REQUESTED)
    elif template == "constrained":
        out.cpu.cores = ProfileField(value=2, status=FieldStatus.REQUESTED)
        out.memory.total_mb = ProfileField(value=4096, status=FieldStatus.REQUESTED)
    elif template == "raspberry-pi-ish":
        out.cpu.cores = ProfileField(value=4, status=FieldStatus.REQUESTED)
        out.cpu.architecture = ProfileField(value="aarch64", status=FieldStatus.REQUESTED)
        out.memory.total_mb = ProfileField(value=2048, status=FieldStatus.REQUESTED)
        out.network.latency_ms = ProfileField(value=40.0, status=FieldStatus.REQUESTED)
    return out


class EnvironmentScreen(Screen):
    BINDINGS: ClassVar[list] = [
        ("escape", "app.pop_screen", "Back"),
        ("r", "reconcile", "Reconcile"),
        ("c", "recapture", "Re-capture host"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._profile: EnvironmentProfile | None = None
        self._captured: EnvironmentProfile | None = None

    def compose(self) -> ComposeResult:
        yield Static(" Environment · target profile ", classes="screen-title")
        with Horizontal(id="env-bar"):
            yield Select.from_values(_TEMPLATES, prompt="template", id="env-template", allow_blank=False)
            yield Input(placeholder="load profile.json…", id="env-load")
            yield Button("Reconcile", id="env-reconcile", variant="primary")
            yield Input(placeholder="save as…", id="env-save")
        yield ProfileDiff(id="env-diff")
        with Horizontal(id="env-edit"):
            yield Static("edit:", id="env-edit-label")
            yield Input(placeholder="select a numeric row, type a value, Enter", id="env-edit-input")
        yield Static("ready", id="env-status")
        yield Footer()

    def on_mount(self) -> None:
        self._status("capturing host…")
        self._capture()

    # --- capture / template ------------------------------------------------
    @work(thread=True, exclusive=True)
    def _capture(self) -> None:
        try:
            self.post_message(RunFinished(capture_environment()))
        except Exception as exc:
            self.post_message(RunFinished(None, exc))

    def on_run_finished(self, message: RunFinished) -> None:
        if message.error is not None:
            self._status(f"[red]capture failed: {message.error}[/red]")
            return
        self._profile = message.result
        self._captured = message.result
        self._repaint()
        self._status("host captured · pick a template, edit rows, then Reconcile")

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "env-template" and self._captured is not None:
            self._profile = apply_template(self._captured, str(event.value))
            self._repaint()
            self._status(f"template: {event.value}")

    def action_recapture(self) -> None:
        self._status("re-capturing host…")
        self._capture()

    # --- load / save -----------------------------------------------------------
    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "env-load":
            self._load(event.value.strip())
        elif event.input.id == "env-save":
            self._save(event.value.strip())
        elif event.input.id == "env-edit-input":
            self._apply_edit(event.value.strip())

    def _load(self, path: str) -> None:
        if not path or not Path(path).is_file():
            self._status(f"[red]no such file: {path}[/red]")
            return
        try:
            self._profile = EnvironmentProfile.model_validate_json(
                Path(path).read_text(encoding="utf-8")
            )
        except Exception as exc:
            self._status(f"[red]bad profile: {exc}[/red]")
            return
        self._captured = self._profile
        self._repaint()
        self._status(f"loaded {path}")

    def _save(self, path: str) -> None:
        if not path or self._profile is None:
            return
        Path(path).write_text(self._profile.model_dump_json(indent=2), encoding="utf-8")
        self._status(f"saved {path}")

    # --- inline edit ---------------------------------------------------------
    def on_data_table_row_highlighted(self) -> None:
        diff = self.query_one("#env-diff", ProfileDiff)
        path = diff.path_at_cursor()
        editable = path in EDITABLE
        self.query_one("#env-edit-input", Input).disabled = not editable
        self.query_one("#env-edit-label", Static).update(
            f"edit {path}:" if editable else "edit: (row not editable)"
        )

    def _apply_edit(self, raw: str) -> None:
        if self._profile is None or not raw:
            return
        diff = self.query_one("#env-diff", ProfileDiff)
        path = diff.path_at_cursor()
        if path not in EDITABLE:
            return
        try:
            value = float(raw)
        except ValueError:
            self._status(f"[red]not a number: {raw}[/red]")
            return
        self._profile = set_profile_parameter(self._profile, path, value)
        self.query_one("#env-edit-input", Input).value = ""
        self._repaint()
        self._status(f"set {path} = {value:g}")

    # --- reconcile ----------------------------------------------------------
    def action_reconcile(self) -> None:
        if self._profile is None:
            return
        try:
            self._profile = reconcile_profile_statuses(self._profile)
        except Exception as exc:
            self._status(f"[red]reconcile failed: {exc}[/red]")
            return
        self._repaint()
        counts: dict[str, int] = {}
        for section in ("os", "cpu", "memory", "locale", "network"):
            obj = getattr(self._profile, section, None)
            if obj is None:
                continue
            for name in type(obj).model_fields:
                fld = getattr(obj, name)
                if hasattr(fld, "status"):
                    counts[fld.status] = counts.get(fld.status, 0) + 1
        summary = "  ".join(f"{k}={v}" for k, v in counts.items())
        self._status(f"reconciled against this host:  {summary}")

    # --- helpers ----------------------------------------------------------------
    def _repaint(self) -> None:
        if self._profile is not None:
            self.query_one("#env-diff", ProfileDiff).show(self._profile)

    def _status(self, text: str) -> None:
        self.query_one("#env-status", Static).update(text)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "env-reconcile":
            self.action_reconcile()
