"""Morph's command-palette provider (``Ctrl+P``).

Navigation, the current screen's run / cancel / save actions, opening a
connected project straight into Experiment, theme toggle, help.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import partial

from textual.command import DiscoveryHit, Hit, Hits, Provider

SCREENS = ("experiment", "monitor", "threshold", "environment", "projects", "regressions")


class MorphCommands(Provider):
    def _commands(self) -> list[tuple[str, str, Callable[[], object]]]:
        app = self.app
        screen = self.screen
        cmds: list[tuple[str, str, Callable[[], object]]] = [
            ("Home", "back to mission control", partial(app.action_home)),
        ]
        for name in SCREENS:
            cmds.append((f"Open {name}", f"go to the {name} screen", partial(app.action_goto, name)))

        kind = screen.__class__.__name__
        if kind == "ExperimentScreen":
            cmds += [
                ("Run experiment", "start causal isolation with the current setup", screen.action_run),
                ("Toggle sequential / batch", "switch the experiment design", screen.action_toggle_mode),
                ("Save regression", "freeze the last verdict as a replayable bundle", screen.action_save),
            ]
            cmds.append(("Load profile…", "type a profile path", partial(screen.focus_profile)))
        elif kind == "ThresholdScreen":
            cmds.append(("Run threshold search", "locate the failure boundary", partial(screen.action_run)))
            cmds.append(
                ("Toggle bayesian / bisection", "switch the search method", screen.action_toggle_method)
            )
            cmds.append(("Load profile…", "type a profile path", partial(screen.focus_profile)))
        elif kind == "RegressionsScreen":
            cmds.append(("Replay regression", "re-run the selected bundle", partial(screen.action_replay)))
            cmds.append(("Export CI test", "write the pytest invariant", partial(screen.action_export)))
        elif kind == "MonitorScreen":
            cmds.append(("Run once", "run the command under the current sliders", screen.action_run_once))
            cmds.append(("Toggle auto-run", "re-run on every slider change", screen.action_toggle_auto))
        elif kind == "EnvironmentScreen":
            cmds.append(("Reconcile", "stamp every field for this host", partial(screen.action_reconcile)))
            cmds.append(("Re-capture host", "capture this machine again", partial(screen.action_recapture)))
        else:
            cmds += [
                ("Run experiment", "open Experiment and run", partial(app.action_goto, "experiment", "run")),
                ("Run threshold search", "open Threshold and search",
                 partial(app.action_goto, "threshold", "run")),
                ("Load profile…", "open Experiment with the profile box focused",
                 partial(app.action_goto, "experiment", "profile")),
            ]

        if getattr(screen, "busy", False):
            cmds.append(("Cancel run", "stop after the current trial", partial(screen.action_cancel)))

        try:
            from morph import projects as _projects

            for proj in _projects.list_projects():
                cmds.append(
                    (f"Open project {proj.name}", proj.command or proj.path, partial(app.open_project, proj))
                )
        except Exception:
            pass

        cmds.append(("Toggle theme", "morph-dark ↔ morph-light", partial(app.action_toggle_theme)))
        cmds.append(("Help", "every key on this screen", partial(app.action_help)))
        cmds.append(("Quit", "leave Morph", partial(app.action_quit)))
        return cmds

    async def discover(self) -> Hits:
        for name, help_text, callback in self._commands():
            yield DiscoveryHit(name, callback, help=help_text)

    async def search(self, query: str) -> Hits:
        matcher = self.matcher(query)
        for name, help_text, callback in self._commands():
            score = matcher.match(name)
            if score > 0:
                yield Hit(score, matcher.highlight(name), callback, help=help_text)
