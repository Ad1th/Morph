"""Environment screen -- capture the host, shape a target profile, and see it
reconciled field-by-field (REPRODUCED / APPROXIMATED / UNAVAILABLE).
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widgets import Button, Footer, Input, Label, Select, Static

from morph.profiler.capture import capture_environment
from morph.schema.profile import EnvironmentProfile, FieldStatus, ProfileField
from morph.tui.orchestrator import set_profile_parameter
from morph.tui.profiles import blank_network, fidelity_badges
from morph.tui.screens.base import MorphScreen
from morph.tui.widgets.profile_diff import EDITABLE, ProfileDiff
from morph.tui.widgets.status_bar import StatusBar

_TEMPLATES = ("host (as captured)", "high-latency", "constrained", "raspberry-pi-ish")


def _ensure_network(profile: EnvironmentProfile) -> None:
    if profile.network is None:
        profile.network = blank_network()


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


class CaptureDone(Message):
    """Host capture landed (or failed)."""

    def __init__(self, profile: EnvironmentProfile | None, error: Exception | None = None) -> None:
        self.profile = profile
        self.error = error
        super().__init__()


class ReconcileDone(Message):
    """Reconcile pass landed (or failed)."""

    def __init__(
        self,
        profile: EnvironmentProfile | None,
        notes: dict[str, str],
        error: Exception | None = None,
    ) -> None:
        self.profile = profile
        self.notes = notes
        self.error = error
        super().__init__()


class EnvironmentScreen(MorphScreen):
    SECTION = "environment"
    SUBTITLE = "target profile"

    BINDINGS: ClassVar[list] = [
        Binding("escape", "app.pop_screen", "Back"),
        Binding("ctrl+r", "reconcile", "Reconcile", priority=True),
        Binding("ctrl+n", "recapture", "Re-capture host", priority=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._profile: EnvironmentProfile | None = None
        self._captured: EnvironmentProfile | None = None
        self._notes: dict[str, str] = {}
        self._busy = False

    def compose(self) -> ComposeResult:
        yield self.title_widget()
        with Vertical(id="env-setup", classes="setup"):
            with Horizontal(classes="row"):
                yield Label("template")
                yield Select.from_values(
                    _TEMPLATES, prompt="template", id="env-template", allow_blank=False, compact=True
                )
                yield Button("Reconcile", id="env-reconcile", variant="primary", compact=True)
            with Horizontal(classes="row"):
                yield Label("load")
                yield Input(placeholder="profile.json → enter", id="env-load", compact=True)
                yield Label("save as")
                yield Input(placeholder="target.json → enter", id="env-save", compact=True)
        yield ProfileDiff(id="env-diff")
        with Horizontal(id="env-edit"):
            yield Static("edit:", id="env-edit-label")
            yield Input(
                placeholder="select a numeric row, type a value, enter", id="env-edit-input", compact=True
            )
        yield StatusBar()
        yield Footer()

    def on_mount(self) -> None:
        self.status("capturing host…")
        self.query_one("#env-diff", ProfileDiff).loading = True
        self._capture()

    # --- capture / template ------------------------------------------------
    @work(thread=True, exclusive=True, group="env-capture")
    def _capture(self) -> None:
        try:
            self.post_message(CaptureDone(capture_environment()))
        except Exception as exc:
            self.post_message(CaptureDone(None, exc))

    def on_capture_done(self, message: CaptureDone) -> None:
        self.query_one("#env-diff", ProfileDiff).loading = False
        if message.error is not None:
            self.status(Text(f"capture failed: {message.error}"), error=True)
            return
        self._profile = message.profile
        self._captured = message.profile
        self._notes = {}
        self._repaint()
        self.status("host captured · pick a template, edit rows, then ^r to reconcile")

    def on_reconcile_done(self, message: ReconcileDone) -> None:
        self.query_one("#env-diff", ProfileDiff).loading = False
        self._busy = False
        if message.error is not None or message.profile is None:
            self.status(Text(f"reconcile failed: {message.error}"), error=True)
            return
        self._profile = message.profile
        self._notes = message.notes
        self._repaint()
        counts: dict[str, int] = {}
        for section in ("os", "cpu", "memory", "locale", "network"):
            obj = getattr(self._profile, section, None)
            if obj is None:
                continue
            for name in type(obj).model_fields:
                fld = getattr(obj, name)
                status = getattr(fld, "status", None)
                if status is not None:
                    key = str(getattr(status, "value", status))
                    counts[key] = counts.get(key, 0) + 1
        summary = "  ".join(f"{k} {v}" for k, v in sorted(counts.items()))
        self.status(f"reconciled against this host → {summary}", ok=True)

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "env-template" and self._captured is not None:
            self._profile = apply_template(self._captured, str(event.value))
            self._notes = {}
            self._repaint()
            self.status(f"template → {event.value}")

    def action_recapture(self) -> None:
        self.status("re-capturing host…")
        self.query_one("#env-diff", ProfileDiff).loading = True
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
            self.status(Text(f"no such file: {path}"), error=True)
            return
        try:
            self._profile = EnvironmentProfile.model_validate_json(
                Path(path).read_text(encoding="utf-8")
            )
        except Exception as exc:
            self.status(Text(f"bad profile: {exc}"), error=True)
            return
        self._captured = self._profile
        self._notes = {}
        self._repaint()
        self.status(Text(f"loaded {path}"), ok=True)

    def _save(self, path: str) -> None:
        if not path:
            return
        if self._profile is None:
            self.status("nothing to save yet", error=True)
            return
        try:
            Path(path).write_text(self._profile.model_dump_json(indent=2), encoding="utf-8")
        except OSError as exc:
            self.status(Text(f"save failed: {exc}"), error=True)
            return
        self.status(Text(f"saved {path}"), ok=True)

    # --- inline edit ---------------------------------------------------------
    def on_data_table_row_highlighted(self) -> None:
        diff = self.query_one("#env-diff", ProfileDiff)
        path = diff.path_at_cursor()
        editable = path in EDITABLE
        self.query_one("#env-edit-input", Input).disabled = not editable
        self.query_one("#env-edit-label", Static).update(
            f"edit {path} →" if editable else "edit: (row not editable)"
        )

    def on_data_table_row_selected(self) -> None:
        if not self.query_one("#env-edit-input", Input).disabled:
            self.query_one("#env-edit-input", Input).focus()

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
            self.status(Text(f"not a number: {raw}"), error=True)
            return
        self._profile = set_profile_parameter(self._profile, path, value)
        self.query_one("#env-edit-input", Input).value = ""
        self._repaint()
        self.status(f"set {path} = {value:g}")

    # --- reconcile ----------------------------------------------------------
    def action_reconcile(self) -> None:
        if self._profile is None or self._busy:
            return
        self._busy = True
        self.status("reconciling…")
        self.query_one("#env-diff", ProfileDiff).loading = True
        self._reconcile_worker(self._profile)

    @work(thread=True, exclusive=True, group="env-reconcile")
    def _reconcile_worker(self, profile: EnvironmentProfile) -> None:
        from morph.runtime.controller import reconcile_profile_statuses

        try:
            reconciled = reconcile_profile_statuses(profile)
            notes = {param: note for param, (_status, note) in fidelity_badges(profile).items() if note}
            self.post_message(ReconcileDone(reconciled, notes))
        except Exception as exc:
            self.post_message(ReconcileDone(None, {}, exc))

    # --- helpers ----------------------------------------------------------------
    def _repaint(self) -> None:
        if self._profile is not None:
            self.query_one("#env-diff", ProfileDiff).show(self._profile, self._notes)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "env-reconcile":
            self.action_reconcile()
