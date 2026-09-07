"""Threshold search screen -- a gauge that converges on the failure boundary.

Bayesian (default): probabilistic bisection; every ``search_probe`` narrows
the credible band and moves the posterior median; ``phase_done`` locks it, or
reports that there is no boundary in range. Classic bisection is one toggle
away and drives the same gauge with its safe / fail bracket.
"""

from __future__ import annotations

from typing import ClassVar

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Button, Checkbox, Footer, Input, Label, RichLog, Select, Static

from morph.config import load_config
from morph.schema.comparison import ThresholdResult
from morph.schema.events import TrialEvent
from morph.tui.messages import RunFinished
from morph.tui.orchestrator import THRESHOLD_PARAMETERS, run_threshold_live
from morph.tui.profiles import BLANK_HINT, PARAMS, resolve_profile
from morph.tui.screens.base import RunnerScreen
from morph.tui.theme import palette
from morph.tui.widgets.status_bar import StatusBar
from morph.tui.widgets.threshold_gauge import ThresholdGauge

_EMPTY = "no search yet · pick a parameter and range, then ^r"


class ThresholdScreen(RunnerScreen):
    SECTION = "threshold"
    SUBTITLE = "failure boundary"

    BINDINGS: ClassVar[list] = [
        *RunnerScreen.BINDINGS,
        Binding("ctrl+r", "run", "Search", priority=True),
        Binding("ctrl+t", "toggle_method", "Bayes/Bisect", priority=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._cfg = load_config()
        self._gauge: ThresholdGauge | None = None
        self._method = "bayesian"
        self._result: ThresholdResult | None = None

    def compose(self) -> ComposeResult:
        yield self.title_widget()
        with Vertical(id="th-setup", classes="setup"):
            with Horizontal(classes="row"):
                yield Label("parameter")
                yield Select.from_values(
                    THRESHOLD_PARAMETERS, prompt="parameter", id="th-param",
                    allow_blank=False, compact=True,
                )
                yield Label("low")
                yield Input(placeholder="low", value="0", id="th-low", classes="narrow", compact=True)
                yield Label("high")
                yield Input(placeholder="high", value="400", id="th-high", classes="narrow", compact=True)
                yield Label("trials")
                yield Input(placeholder="trials", value="24", id="th-trials", classes="narrow", compact=True)
            with Horizontal(classes="row"):
                yield Label("profile")
                yield Input(placeholder=BLANK_HINT, id="th-profile", compact=True)
                yield Label("command")
                yield Input(
                    value=self.project_command or self._cfg.default_command or "",
                    placeholder="python -m apps.pool_retry",
                    id="th-command",
                    compact=True,
                )
                yield Checkbox("bayesian", value=True, id="th-bayes", compact=True)
                yield Button("Search ▶", id="th-run", variant="primary", compact=True)
                yield Button("Stop", id="th-stop", compact=True, disabled=True)
        with Vertical(id="th-body"):
            with Container(id="th-gauge-wrap"):
                yield Static(_EMPTY, id="th-empty")
            yield RichLog(id="th-log", classes="panel", markup=True, wrap=True, highlight=False)
        yield StatusBar()
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#th-log", RichLog).border_title = "PROBES"
        self.query_one("#th-command", Input).focus()
        if self.demo:
            self.status("DEMO · ^r replays a recorded Bayesian search along latency at 18 % loss")
        else:
            self.status("bayesian: trials = total budget · bisection: trials per probe")

    def focus_profile(self) -> None:
        self.query_one("#th-profile", Input).focus()

    @property
    def method(self) -> str:
        return self._method

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "th-param":
            spec = PARAMS.get(str(event.value))
            if spec:
                self.query_one("#th-low", Input).value = f"{spec['low']:g}"
                self.query_one("#th-high", Input).value = f"{spec['high']:g}"

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        if event.checkbox.id == "th-bayes":
            self._method = "bayesian" if event.value else "bisection"
            self.status(f"method → {self._method}")

    def action_toggle_method(self) -> None:
        box = self.query_one("#th-bayes", Checkbox)
        box.value = not box.value

    # --- run ----------------------------------------------------------------
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "th-run":
            self.action_run()
        elif event.button.id == "th-stop":
            self.action_cancel()

    def _num(self, widget_id: str, label: str) -> float | None:
        raw = self.query_one(widget_id, Input).value.strip()
        try:
            return float(raw)
        except (ValueError, TypeError):
            self.status(f"{label} must be a number, got {raw!r}", error=True)
            self.query_one(widget_id, Input).focus()
            return None

    def _log(self, text: str | Text) -> None:
        self.query_one("#th-log", RichLog).write(text)

    def _mount_gauge(self, parameter: str, low: float, high: float) -> ThresholdGauge:
        wrap = self.query_one("#th-gauge-wrap", Container)
        wrap.remove_children()
        spec = PARAMS.get(parameter, {})
        gauge = ThresholdGauge(parameter, low, high, unit=spec.get("unit", ""),
                               bayesian=self._method == "bayesian")
        gauge.add_class("panel")
        wrap.mount(gauge)
        self._gauge = gauge
        self.query_one("#th-log", RichLog).clear()
        return gauge

    def _set_running(self, running: bool) -> None:
        self.query_one("#th-run", Button).disabled = running
        self.query_one("#th-stop", Button).disabled = not running
        self.query_one("#th-bayes", Checkbox).disabled = running

    def action_run(self) -> None:
        if self.busy:
            self.status("already running · esc / c stops it")
            return
        p = palette(self)
        if self.demo:
            from morph.tui.demo import play, threshold_recording

            events, result = threshold_recording()
            self._method = "bayesian"
            self.query_one("#th-bayes", Checkbox).value = True
            self.query_one("#th-param", Select).value = "network.latency_ms"
            self._result = result
            self._mount_gauge("network.latency_ms", 0.0, 400.0)
            self._log(Text("DEMO  replaying the engine's recorded Bayesian search of "
                           "apps/pool_retry along latency at 18 % loss", style=p.muted))
            self._set_running(True)
            self.start(lambda on_event: play(on_event, events), phase="threshold", total=result.trials or 24)
            return

        command = self.query_one("#th-command", Input).value.strip()
        if not command:
            self.status("enter a command first", error=True)
            self.query_one("#th-command", Input).focus()
            return
        parameter = str(self.query_one("#th-param", Select).value)
        low = self._num("#th-low", "low")
        high = self._num("#th-high", "high")
        trials_f = self._num("#th-trials", "trials")
        if low is None or high is None or trials_f is None:
            return
        trials = int(trials_f)
        if trials < 2:
            self.status("trials must be at least 2", error=True)
            return
        if high <= low:
            self.status("high must exceed low", error=True)
            return
        try:
            profile = resolve_profile(self.query_one("#th-profile", Input).value)
        except Exception as exc:
            self.status(Text(f"bad profile: {exc}"), error=True)
            self.query_one("#th-profile", Input).focus()
            return

        self._result = None
        self._mount_gauge(parameter, low, high)
        budget = f"{trials} trials total" if self._method == "bayesian" else f"{trials} trials/probe"
        self._log(Text(f"{self._method}: {parameter} in [{low:g}, {high:g}] · {budget}", style=p.muted))
        self._set_running(True)
        self.start(
            run_threshold_live, profile, command, parameter, low, high, trials, 30.0,
            cwd=self.project_cwd, method=self._method,
            phase="threshold", total=trials if self._method == "bayesian" else 0,
        )

    # --- events -----------------------------------------------------------
    def handle_event(self, ev: TrialEvent) -> None:
        gauge = self._gauge
        if gauge is None:
            return
        p = palette(self)
        if ev.kind == "search_probe":
            passed = ev.passed if ev.passed is not None else bool(ev.extra.get("passed"))
            probs = {k: float(v) for k, v in ev.extra.items()
                     if k in ("boundary_in_range", "never_fails", "always_fails")}
            gauge.probe(
                ev.param_value or 0.0, passed, ev.safe_value, ev.failure_value,
                estimate=ev.boundary_estimate, probs=probs or None,
            )
            line = Text()
            line.append(f"probe {ev.param_value:.4g}  ", style=p.text)
            line.append("pass" if passed else "FAIL", style=p.pass_ if passed else p.fail)
            if gauge.bayesian and ev.safe_value is not None and ev.failure_value is not None:
                line.append(f"   credible [{ev.safe_value:.3g}, {ev.failure_value:.3g}]", style=p.muted)
                if ev.boundary_estimate is not None:
                    line.append(f"  median {ev.boundary_estimate:.3g}", style=p.evidence)
            elif ev.total:
                line.append(f"   {ev.failures}/{ev.total} failed", style=p.muted)
            self._log(line)
        elif ev.kind == "phase_done":
            outcome = None
            probs = {k: float(v) for k, v in ev.extra.items()
                     if k in ("boundary_in_range", "never_fails", "always_fails")}
            if ev.boundary_estimate is None and probs:
                if probs.get("boundary_in_range", 0.0) < 0.5:
                    never, always = probs.get("never_fails", 0), probs.get("always_fails", 0)
                    outcome = "never_fails" if never >= always else "always_fails"
            posterior = self._result.posterior if self._result is not None else None
            gauge.finish(ev.boundary_estimate, ev.safe_value, ev.failure_value,
                         outcome=outcome, posterior=posterior, probs=probs or None)

    def run_finished(self, message: RunFinished) -> None:
        self._set_running(False)
        p = palette(self)
        if message.cancelled:
            self._log(Text("cancelled", style=p.warn))
            return
        if message.error is not None:
            self._log(Text(f"search failed: {message.error}", style=p.fail))
            return
        result = message.result if isinstance(message.result, ThresholdResult) else self._result
        gauge = self._gauge
        if isinstance(result, ThresholdResult) and gauge is not None:
            self._result = result
            outcome = getattr(result, "outcome", None)
            if outcome is None and result.boundary_estimate is None:
                never = result.probability_never_fails or 0.0
                always = result.probability_always_fails or 0.0
                outcome = "never_fails" if never >= always else "always_fails"
            probs = {
                "boundary_in_range": result.probability_boundary_in_range,
                "never_fails": result.probability_never_fails,
                "always_fails": result.probability_always_fails,
            }
            gauge.finish(
                result.boundary_estimate,
                result.credible_low if result.credible_low is not None else result.safe_value,
                result.credible_high if result.credible_high is not None else result.failure_value,
                outcome=outcome,
                posterior=result.posterior or None,
                probs={k: v for k, v in probs.items() if v is not None} or None,
            )
            if result.boundary_estimate is not None:
                unit = PARAMS.get(result.parameter, {}).get("unit", "")
                self.status(Text(f"boundary ≈ {result.boundary_estimate:.3g} {unit}".rstrip()), ok=True)
            else:
                self.status("no boundary in range", ok=True)
        self._log(Text("done", style=p.pass_))
