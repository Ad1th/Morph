"""Typer CLI interface for Morph.

Conventions every subcommand follows:

* ``--profile/-p``, ``--command/-c``, ``--project``, ``--cwd``, ``--trials/-n``,
  ``--timeout``, ``--json`` mean the same thing everywhere.
* With ``--json`` stdout carries exactly one JSON document and nothing else;
  every diagnostic and progress line goes to stderr, so ``morph ... --json | jq``
  always works.
* Exit codes: ``0`` success (or "no effect"), ``1`` a failure *result* (the run
  failed, a replay violated its invariant, an experiment found an effect),
  ``2`` usage or setup error (bad flags, missing file, malformed profile, a
  command that cannot launch), ``3`` threshold search found no boundary in the
  range, ``124`` the run timed out, ``128+n`` the run died from signal ``n``.

Orchestration lives in :mod:`morph.api.service`, shared with the API server;
this module is presentation. Heavy imports (engine, runtime, uvicorn) happen
inside the commands so ``morph --help`` stays fast.
"""

from __future__ import annotations

import json
import os
from enum import StrEnum
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from morph.api import defaults

EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_USAGE = 2
EXIT_NO_BOUNDARY = 3
EXIT_TIMEOUT = 124

_EPILOG = (
    "Exit codes: 0 success / no effect; 1 failure result (run failed, replay violated, "
    "effect found); 2 usage or setup error (bad flags, missing file, malformed profile, "
    "command cannot launch); 3 threshold found no boundary in range; 124 run timed out."
)

app = typer.Typer(
    name="morph",
    help="Morph: test software in environments you don't physically have.",
    epilog=_EPILOG,
    context_settings={"help_option_names": ["-h", "--help"]},
    no_args_is_help=True,
    rich_markup_mode="rich",
)

#: Human output (tables, panels). Never used in --json mode.
console = Console()
#: Diagnostics and progress: always stderr, so stdout stays machine-readable.
err = Console(stderr=True)

PANEL_PROJECTS = "Projects"
PANEL_ENVS = "Environments"
PANEL_RUN = "Run & experiment"
PANEL_REG = "Regressions"
PANEL_UI = "Interfaces & health"


class ExperimentMode(StrEnum):
    sequential = "sequential"
    batch = "batch"


class ThresholdMethod(StrEnum):
    bayes = "bayes"
    bisect = "bisect"


class Template(StrEnum):
    default = "default"
    high_latency = "high-latency"
    constrained = "constrained"


# --------------------------------------------------------------------------- #
# shared helpers
# --------------------------------------------------------------------------- #


def _fail(message: str, code: int = EXIT_USAGE, *, as_json: bool = False, kind: str = "error") -> None:
    """Print one error line (stderr) and exit. In JSON mode stdout gets an error object."""
    err.print(f"[bold red]Error:[/bold red] {escape(message)}", highlight=False)
    if as_json:
        print(json.dumps({"error": kind, "detail": message}))
    raise typer.Exit(code=code)


def _emit_json(payload: Any) -> None:
    if hasattr(payload, "model_dump_json"):
        print(payload.model_dump_json())
    else:
        print(json.dumps(payload, default=str))


def _load_profile(path: Path, *, as_json: bool = False):
    from morph.api import service

    try:
        return service.load_profile_file(path)
    except service.ProfileLoadError as exc:
        _fail(str(exc), as_json=as_json, kind="profile_error")


def _resolve_project(
    project: str | None, command: str | None, cwd: str | None, *, as_json: bool = False
) -> tuple[str, str | None]:
    """Fill in `command` / `cwd` from a registered project when `--project` is
    given. An explicit `--command` still wins. Returns (command, cwd)."""
    if project:
        from morph import projects as _projects

        try:
            proj = _projects.load(project)
        except KeyError as exc:
            _fail(str(exc), as_json=as_json, kind="no_project")
        command = command or proj.command
        cwd = cwd or proj.cwd
        if not command:
            _fail(
                f"project '{proj.name}' has no detected command; pass --command",
                as_json=as_json, kind="no_command",
            )
    if not command or not command.strip():
        _fail("one of --command or --project is required", as_json=as_json, kind="usage")
    return command, cwd


def _run_exit_code(result) -> int:
    """Shell-friendly exit code for a RunResult."""
    from morph.api import service

    if result.passed:
        return EXIT_OK
    if service.is_setup_error(result):
        return EXIT_USAGE
    if result.error_type == "TimeoutExpired":
        return EXIT_TIMEOUT
    code = result.exit_code
    if code is None or code == 0:
        return EXIT_FAILURE
    if code < 0:
        return 128 + abs(code)
    return code


def _progress_printer():
    """A compact stderr line per engine event (never stdout)."""

    def _on_event(event) -> None:
        kind = event.kind
        if kind == "trial":
            mark = "[green]pass[/green]" if event.passed else (
                "[yellow]invalid[/yellow]" if event.passed is None else "[red]FAIL[/red]"
            )
            idx = (event.trial_index or 0) + 1
            total = f"/{event.total}" if event.total else ""
            err.print(
                f"  [dim]{event.condition:<16}[/dim] trial {idx}{total}: {mark}"
                + (f"  [dim]{event.duration_ms:.0f} ms[/dim]" if event.duration_ms else ""),
                highlight=False,
            )
        elif kind == "evidence":
            flag = "  [bold green]decisive[/bold green]" if event.decisive else ""
            err.print(
                f"  [dim]{event.condition:<16}[/dim] E = {event.e_value:.3g} "
                f"(threshold {event.evidence_threshold:.0f}, {event.pairs} pairs){flag}",
                highlight=False,
            )
        elif kind == "search_probe":
            mark = "[green]pass[/green]" if event.extra.get("passed") else "[red]FAIL[/red]"
            est = f"  est {event.boundary_estimate:.2f}" if event.boundary_estimate is not None else ""
            err.print(f"  probe {event.param_value:.2f}: {mark}{est}", highlight=False)
        elif kind == "phase_start" and event.phase == "probe":
            err.print("  [dim]probing that the command launches...[/dim]")

    return _on_event


def _version_callback(value: bool) -> None:
    if value:
        import morph

        print(f"morph {morph.__version__}")
        raise typer.Exit()


@app.callback()
def _main(
    version: bool = typer.Option(
        False, "--version", "-V", help="Print the Morph version and exit",
        callback=_version_callback, is_eager=True,
    ),
) -> None:
    """Morph: test software in environments you don't physically have."""


# --------------------------------------------------------------------------- #
# projects: `morph connect` a repo/dir once, then `--project <id>` everywhere
# --------------------------------------------------------------------------- #


@app.command(rich_help_panel=PANEL_PROJECTS)
def connect(
    source: str = typer.Argument(..., help="owner/repo, a GitHub URL, or a local directory path"),
    branch: str | None = typer.Option(None, "--branch", "-b", help="Branch to clone"),
    token: str | None = typer.Option(None, "--token", help="GitHub token (else gh CLI / env)"),
    install: bool = typer.Option(
        True, "--install/--no-install",
        help="Build an isolated venv and install the project's dependencies (default: on)",
    ),
    name: str | None = typer.Option(None, "--name", help="Registry name (default: repo/dir name)"),
    as_json: bool = typer.Option(False, "--json", help="Print the project record as JSON only"),
):
    """Add a GitHub repo or local directory as a runnable project."""
    from morph import github, project_setup

    err.print(
        f"[cyan]Connecting[/cyan] {escape(source)} …  [dim](auth: {github.token_source(token)})[/dim]"
    )
    try:
        proj = project_setup.connect(
            source, token=token, branch=branch, install=install, name=name,
            logger=lambda m: err.print(f"  [dim]{m}[/dim]", highlight=False),
        )
    except (github.GitHubError, FileNotFoundError) as exc:
        _fail(str(exc), as_json=as_json, kind="connect_error")

    if as_json:
        _emit_json(proj)
        return
    _print_project(proj)
    if proj.deps_failed:
        console.print(
            f"[yellow]note:[/yellow] {len(proj.deps_failed)} dependency step(s) failed "
            f"({', '.join(proj.deps_failed)}). Retry with:  morph reinstall {proj.id}"
        )
    console.print(f"\n[green]next:[/green]  morph experiment --project {proj.id}")


def _print_project(proj) -> None:
    table = Table(title=f"Connected: {proj.name}", show_header=False)
    table.add_column(style="cyan")
    table.add_column(style="white")
    table.add_row("id", proj.id)
    table.add_row("source", proj.source + (f"  ({proj.repo}@{proj.commit})" if proj.repo else ""))
    table.add_row("path", proj.path)
    table.add_row("command", proj.command or "[yellow]not detected — pass --command[/yellow]")
    if proj.venv:
        table.add_row("venv", proj.venv)
    if proj.deps_failed:
        table.add_row("deps", f"[yellow]{len(proj.deps_failed)} failed[/yellow]")
    table.add_row("files", str(proj.file_count))
    console.print(table)


@app.command(rich_help_panel=PANEL_PROJECTS)
def reinstall(
    project: str = typer.Argument(..., help="Connected project id or name"),
):
    """Rebuild a connected project's venv and re-install its dependencies (no re-clone)."""
    from morph import project_setup
    from morph import projects as _projects

    try:
        proj = _projects.load(project)
    except KeyError as exc:
        _fail(str(exc))

    err.print(f"[cyan]Reinstalling[/cyan] {proj.name} …")
    updated = project_setup.reinstall(
        proj, logger=lambda m: err.print(f"  [dim]{m}[/dim]", highlight=False)
    )
    _print_project(updated)
    if updated.deps_failed:
        console.print(f"[yellow]still failing:[/yellow] {', '.join(updated.deps_failed)}")
        raise typer.Exit(code=EXIT_FAILURE)
    console.print("[green]all dependencies installed.[/green]")


@app.command(rich_help_panel=PANEL_PROJECTS)
def projects(
    remove: str | None = typer.Option(None, "--rm", help="Delete a project by id or name"),
    as_json: bool = typer.Option(False, "--json", help="Print the registry as JSON only"),
):
    """List connected projects (or --rm one)."""
    from morph import projects as _projects

    if remove:
        ok = _projects.delete(remove)
        if as_json:
            _emit_json({"removed": ok, "project": remove})
        elif ok:
            console.print(f"[green]removed[/green] {remove}")
        else:
            err.print(f"[yellow]no such project:[/yellow] {remove}")
        raise typer.Exit(code=EXIT_OK if ok else EXIT_FAILURE)

    rows = _projects.list_projects()
    if as_json:
        print(json.dumps([p.model_dump() for p in rows]))
        return
    if not rows:
        console.print("[dim]no projects — `morph connect <repo|dir>`[/dim]")
        return
    table = Table(title="Connected projects")
    table.add_column("id", style="cyan")
    table.add_column("name")
    table.add_column("source")
    table.add_column("command", style="dim")
    for proj in rows:
        src = proj.source + (f" {proj.repo}@{proj.commit}" if proj.repo else "")
        table.add_row(proj.id, proj.name, src, proj.command or "—")
    console.print(table)


# --------------------------------------------------------------------------- #
# environments
# --------------------------------------------------------------------------- #


@app.command(rich_help_panel=PANEL_ENVS)
def capture(
    output: Path | None = typer.Option(
        None, "--output", "-o", help="Path to save captured profile JSON (default: stdout)"
    ),
    as_json: bool = typer.Option(False, "--json", help="Print the profile as compact JSON only"),
):
    """Capture the physical environment of the current machine."""
    from morph.profiler.capture import capture_environment

    err.print("[bold cyan]Capturing host environment...[/bold cyan]")
    profile = capture_environment()

    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(profile.model_dump_json(indent=2), encoding="utf-8")
        if as_json:
            _emit_json({"saved": str(output)})
        else:
            console.print(f"[bold green]Profile saved to:[/bold green] {output}")
    elif as_json:
        _emit_json(profile)
    else:
        # Plain JSON on stdout (no Rich colouring) so `morph capture > p.json` is valid.
        print(profile.model_dump_json(indent=2))


@app.command(rich_help_panel=PANEL_ENVS)
def define(
    output: Path = typer.Option("target_profile.json", "--output", "-o", help="Target output file"),
    template: Template = typer.Option(
        Template.default, "--template", "-t", help="Template: default, high-latency, constrained"
    ),
    latency: float = typer.Option(
        defaults.DEMO_LATENCY_MS, "--latency", help="high-latency template: added latency (ms)"
    ),
    loss: float = typer.Option(
        defaults.DEMO_PACKET_LOSS_PERCENT, "--loss", help="high-latency template: packet loss (%)"
    ),
):
    """Generate a template environment profile JSON for editing."""
    from morph.api import service
    from morph.profiler.capture import capture_environment
    from morph.schema.profile import FieldStatus

    base = capture_environment()
    if template is Template.high_latency:
        # 120 ms / 18 % is the validated operating point for the flagship
        # interaction fixture (apps/pool_retry): neither condition alone moves
        # the failure rate, the pair drives it to ~100 %. See apps/README.md.
        base = service.default_target_profile(latency, loss, base=base)
    elif template is Template.constrained:
        if base.cpu and base.cpu.cores:
            base.cpu.cores.value = 2
            base.cpu.cores.status = FieldStatus.REQUESTED
        if base.memory and base.memory.total_mb:
            base.memory.total_mb.value = 4096
            base.memory.total_mb.status = FieldStatus.REQUESTED

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(base.model_dump_json(indent=2), encoding="utf-8")
    console.print(f"[bold green]Template profile ({template.value}) written to:[/bold green] {output}")


# --------------------------------------------------------------------------- #
# run & experiment
# --------------------------------------------------------------------------- #


@app.command(rich_help_panel=PANEL_RUN)
def run(
    command: str | None = typer.Option(None, "--command", "-c", help="Command to execute"),
    project: str | None = typer.Option(None, "--project", help="Connected project id or name"),
    profile: Path | None = typer.Option(None, "--profile", "-p", help="Path to EnvironmentProfile JSON"),
    cwd: str | None = typer.Option(None, "--cwd", help="Working directory for the command"),
    timeout: float = typer.Option(defaults.TIMEOUT_SEC, "--timeout", min=0.001, help="Timeout in seconds"),
    force_proxy: bool = typer.Option(
        False, "--force-proxy", help="Force user-space TCP proxy instead of native OS tools"
    ),
    cloud: bool = typer.Option(
        False, "--cloud", help="Route to the remote worker if this host cannot satisfy the profile"
    ),
    as_json: bool = typer.Option(
        False, "--json", help="Print the RunResult as JSON only (used by remote workers)"
    ),
):
    """Run an application once under a simulated environment profile."""
    from morph.api import service

    command, cwd = _resolve_project(project, command, cwd, as_json=as_json)
    env_profile = _load_profile(profile, as_json=as_json) if profile else None
    if cloud and env_profile is None:
        _fail("--cloud needs a --profile to assess against the worker", as_json=as_json)

    from morph.runtime.controller import RuntimeController

    controller = RuntimeController(force_proxy=force_proxy)
    err.print(
        f"[cyan]Executing:[/cyan] {escape(command)}" + (f"  [dim](cwd: {escape(cwd)})[/dim]" if cwd else ""),
        highlight=False,
    )

    placement = None
    if env_profile and cloud:
        from morph.cloud import NotReproducibleAnywhere, run_anywhere
        from morph.config import load_config

        try:
            result, placement = run_anywhere(
                profile=env_profile, command=command, timeout=timeout,
                controller=controller, cwd=cwd, cloud=load_config().cloud,
            )
        except NotReproducibleAnywhere as exc:
            _fail(str(exc), as_json=as_json, kind="not_reproducible")
    elif env_profile:
        result = controller.run(profile=env_profile, command=command, timeout=timeout, cwd=cwd)
    else:
        from morph.runtime.runner import execute_command

        result = execute_command(command=command, timeout=timeout, cwd=cwd)

    code = _run_exit_code(result)
    setup_error = service.is_setup_error(result)

    # Machine mode: a bare JSON document on stdout and nothing else. This is
    # the contract morph.cloud.worker parses when Morph runs on another box.
    if as_json:
        if setup_error:
            err.print(f"[bold red]Error:[/bold red] {service.setup_error_message(result, command, cwd)}")
        print(result.model_dump_json())
        raise typer.Exit(code=code)

    if setup_error:
        _fail(service.setup_error_message(result, command, cwd))

    if placement is not None and placement.location == "cloud":
        console.print(f"[yellow]Routed to the cloud worker[/yellow] -- {placement.summary}")

    status_style = "bold green" if result.passed else "bold red"
    peak_memory = f"{result.peak_memory_mb:.1f} MB" if result.peak_memory_mb is not None else "N/A"
    err_text = f"\nError: {result.error_type}: {result.error_message}" if not result.passed else ""
    console.print(Panel(
        f"Exit Code: {result.exit_code}\n"
        f"Duration: {result.duration_ms:.1f}ms\n"
        f"Peak Memory: {peak_memory}\n"
        f"Passed: {result.passed}" + err_text,
        title=f"Run Result [{'PASS' if result.passed else 'FAIL'}]",
        border_style=status_style,
    ))

    # Child output is untrusted text: never interpret it as Rich markup.
    if result.stdout:
        console.print("[bold]STDOUT:[/bold]")
        console.print(Text(result.stdout.strip()))
    if result.stderr:
        console.print("[bold red]STDERR:[/bold red]")
        console.print(Text(result.stderr.strip()))

    if code != EXIT_OK:
        raise typer.Exit(code=code)


def _fmt_ci(cmp) -> str:
    if cmp.risk_difference is None:
        return "-"
    text = f"{cmp.risk_difference:+.0%}"
    if cmp.risk_difference_ci:
        lo, hi = cmp.risk_difference_ci
        text += escape(f" [{lo:+.0%}, {hi:+.0%}]")
    return text


def _experiment_table(result) -> Table:
    sequential = any(c.method == "paired_e_value" for c in result.comparisons)
    table = Table(title="Causal Isolation Results")
    table.add_column("Condition", style="cyan", min_width=10)
    table.add_column("Failures", style="magenta", justify="right", min_width=8)
    table.add_column("Rate", style="yellow", justify="right", min_width=4)
    table.add_column("Δ risk (95% CI)", justify="right", min_width=9)
    if sequential:
        table.add_column("E-value (pairs)", style="blue", justify="right", min_width=9)
    table.add_column("p-value", style="blue", justify="right", min_width=7)
    table.add_column("Effect", style="green", min_width=9)

    if result.baseline:
        row = [
            "baseline",
            f"{result.baseline.failures}/{result.baseline.total_runs}",
            f"{result.baseline.failure_rate:.0%}",
            "-",
        ]
        if sequential:
            row.append("-")
        row += ["-", "control"]
        table.add_row(*row)

    for cmp in result.comparisons:
        effect = cmp.effect_label
        if effect == "significant_increase":
            effect = "[bold red]significant increase[/bold red]"
        elif effect == "significant_decrease":
            effect = "[bold green]significant decrease[/bold green]"
        else:
            effect = "[dim]no effect[/dim]"
        row = [
            cmp.condition_label,
            f"{cmp.treatment_failures}/{cmp.treatment_total}",
            f"{cmp.treatment_failure_rate:.0%}",
            _fmt_ci(cmp),
        ]
        if sequential:
            evidence = f"{cmp.e_value:.3g}" if cmp.e_value is not None else "-"
            if cmp.pairs is not None:
                evidence += f" ({cmp.pairs} pairs" + (", stopped early)" if cmp.stopped_early else ")")
            row.append(evidence)
        row += [f"{cmp.p_value:.4f}" if cmp.p_value is not None else "-", effect]
        table.add_row(*row)
    return table


def _print_experiment(result, *, mode: str) -> None:
    console.print(_experiment_table(result))
    verdict_style = {
        "environment_caused": "bold red",
        "environment_exposed": "bold yellow",
        "application_internal": "bold magenta",
        "no_effect": "bold green",
    }.get(result.classification, "bold")
    strongest = result.strongest_condition
    body = f"[{verdict_style}]{result.classification}[/{verdict_style}]"
    if strongest not in ("", "none"):
        body += f"  (strongest: {strongest})"
    body += f"\n{result.summary}"
    for note in getattr(result, "warnings", None) or []:
        if note.strip() in result.summary:
            continue  # the engine already folded it into the summary
        body += f"\n[yellow]note:[/yellow] {escape(note)}"
    console.print(Panel(body, title=f"Verdict ({mode} mode)", border_style=verdict_style))


def _experiment_exit_code(result) -> int:
    return EXIT_OK if result.classification == "no_effect" else EXIT_FAILURE


@app.command(rich_help_panel=PANEL_RUN)
def experiment(
    command: str | None = typer.Option(None, "--command", "-c", help="Command to execute"),
    project: str | None = typer.Option(None, "--project", help="Connected project id or name"),
    profile: Path | None = typer.Option(
        None, "--profile", "-p",
        help="Target EnvironmentProfile JSON (default: this host plus --latency / --loss)",
    ),
    cwd: str | None = typer.Option(None, "--cwd", help="Working directory for every trial"),
    mode: ExperimentMode = typer.Option(
        ExperimentMode.sequential, "--mode",
        help="sequential: paired round-robin trials with anytime-valid e-values and early "
        "stopping; batch: N trials per condition then one Fisher test",
    ),
    trials: int = typer.Option(
        defaults.TRIALS, "--trials", "-n", min=1, help="Trials per condition (batch mode)"
    ),
    max_rounds: int = typer.Option(
        defaults.SEQUENTIAL_MAX_ROUNDS, "--max-rounds", min=1, help="Round budget (sequential mode)"
    ),
    alpha: float = typer.Option(
        defaults.ALPHA, "--alpha", min=1e-6, max=0.999999, help="Family-wise false-positive rate"
    ),
    latency: float = typer.Option(
        defaults.DEMO_LATENCY_MS, "--latency", help="Default target: added latency (ms)"
    ),
    loss: float = typer.Option(
        defaults.DEMO_PACKET_LOSS_PERCENT, "--loss", help="Default target: packet loss (%)"
    ),
    timeout: float = typer.Option(
        defaults.TIMEOUT_SEC, "--timeout", min=0.001, help="Per-trial timeout in seconds"
    ),
    as_json: bool = typer.Option(False, "--json", help="Print the ExperimentResult as JSON only"),
):
    """Isolate which environmental condition makes the command fail."""
    from morph.api import service

    command, cwd = _resolve_project(project, command, cwd, as_json=as_json)
    if profile:
        target = _load_profile(profile, as_json=as_json)
    else:
        target = service.default_target_profile(latency, loss)

    spec = service.IsolationSpec(
        command=command, target_profile=target, cwd=cwd, timeout=timeout,
        mode=mode.value, trials=trials, max_rounds=max_rounds, alpha=alpha,
    )
    if mode is ExperimentMode.sequential:
        budget = f"{max_rounds} rounds max"
    else:
        budget = f"{trials} trials per condition"
    err.print(f"[bold cyan]Running causal experiment ({mode.value}, {budget})...[/bold cyan]")
    try:
        result = service.run_isolation(spec, on_event=_progress_printer())
    except service.setup_error_types() as exc:
        _fail(str(exc), as_json=as_json, kind="setup_error")
    except ValueError as exc:
        _fail(str(exc), as_json=as_json)

    if as_json:
        _emit_json(result)
    else:
        _print_experiment(result, mode=mode.value)
    raise typer.Exit(code=_experiment_exit_code(result))


@app.command(rich_help_panel=PANEL_RUN)
def demo(
    max_rounds: int = typer.Option(
        defaults.SEQUENTIAL_MAX_ROUNDS, "--max-rounds", min=1, help="Round budget"
    ),
    latency: float = typer.Option(defaults.DEMO_LATENCY_MS, "--latency", help="Added latency (ms)"),
    loss: float = typer.Option(defaults.DEMO_PACKET_LOSS_PERCENT, "--loss", help="Packet loss (%)"),
    timeout: float = typer.Option(60.0, "--timeout", min=0.001, help="Per-trial timeout in seconds"),
    as_json: bool = typer.Option(False, "--json", help="Print the ExperimentResult as JSON only"),
):
    """Run the flagship apps/pool_retry experiment end to end (sequential mode).

    Neither latency nor packet loss alone breaks the app; together they do.
    """
    import morph

    repo_root = Path(morph.__file__).resolve().parent.parent
    if not (repo_root / "apps" / "pool_retry" / "__main__.py").is_file():
        _fail(
            f"apps/pool_retry is not next to this morph checkout ({repo_root}); "
            "run the demo from a source checkout", as_json=as_json,
        )
    err.print(
        f"[bold cyan]Demo:[/bold cyan] {defaults.DEMO_COMMAND} under {latency:.0f} ms / {loss:.0f} % loss "
        f"(sequential, {max_rounds} rounds max)"
    )
    experiment(
        command=defaults.DEMO_COMMAND, project=None, profile=None, cwd=str(repo_root),
        mode=ExperimentMode.sequential, trials=defaults.TRIALS, max_rounds=max_rounds,
        alpha=defaults.ALPHA, latency=latency, loss=loss, timeout=timeout, as_json=as_json,
    )


@app.command(rich_help_panel=PANEL_RUN)
def threshold(
    command: str | None = typer.Option(None, "--command", "-c", help="Command to execute"),
    project: str | None = typer.Option(None, "--project", help="Connected project id or name"),
    profile: Path | None = typer.Option(
        None, "--profile", "-p", help="Base EnvironmentProfile JSON (default: captured host)"
    ),
    cwd: str | None = typer.Option(None, "--cwd", help="Working directory for every trial"),
    parameter: str = typer.Option(..., "--parameter", help="Parameter to search (e.g. network.latency_ms)"),
    low: float = typer.Option(defaults.THRESHOLD_LOW, "--low", help="Lower bound value"),
    high: float = typer.Option(defaults.THRESHOLD_HIGH, "--high", help="Upper bound value"),
    method: ThresholdMethod = typer.Option(
        ThresholdMethod.bayes, "--method",
        help="bayes: probabilistic bisection with a credible interval (noise-aware); "
        "bisect: deterministic halving, --trials runs per probe",
    ),
    trials: int = typer.Option(
        defaults.THRESHOLD_TRIALS, "--trials", "-n", min=1, help="Trials per probe (bisect)"
    ),
    max_trials: int = typer.Option(
        defaults.THRESHOLD_MAX_TRIALS, "--max-trials", min=1, help="Total trial budget (bayes)"
    ),
    precision: float | None = typer.Option(
        None, "--precision", min=1e-9, help="Stop width (default: 2%% of the range)"
    ),
    timeout: float = typer.Option(
        defaults.TIMEOUT_SEC, "--timeout", min=0.001, help="Per-trial timeout in seconds"
    ),
    as_json: bool = typer.Option(False, "--json", help="Print the ThresholdResult as JSON only"),
):
    """Locate the value of one parameter at which failures begin."""
    from morph.api import service

    command, cwd = _resolve_project(project, command, cwd, as_json=as_json)
    if high <= low:
        _fail(f"--high ({high}) must be greater than --low ({low})", as_json=as_json)
    base = _load_profile(profile, as_json=as_json) if profile else None

    spec = service.ThresholdSpec(
        command=command, parameter=parameter, low=low, high=high, profile=base, cwd=cwd,
        timeout=timeout, method=method.value, trials=trials, precision=precision,
        max_trials=max_trials,
    )
    err.print(
        f"[bold cyan]Searching threshold for '{escape(parameter)}' in "
        + escape(f"[{low}, {high}]")
        + f" ({method.value}, precision {spec.effective_precision:g})...[/bold cyan]"
    )
    try:
        thresh = service.run_threshold(spec, on_event=_progress_printer())
    except service.setup_error_types() as exc:
        _fail(str(exc), as_json=as_json, kind="setup_error")
    except ValueError as exc:
        _fail(str(exc), as_json=as_json)

    found = thresh.outcome == "boundary_found"
    if as_json:
        _emit_json(thresh)
        raise typer.Exit(code=EXIT_OK if found else EXIT_NO_BOUNDARY)

    def num(v) -> str:
        return f"{v:.2f}" if v is not None else "none"

    lines = [
        f"Parameter:         {thresh.parameter}",
        f"Method:            {thresh.method}",
        f"Outcome:           {thresh.outcome}",
        f"Boundary estimate: {num(thresh.boundary_estimate)}"
        + ("" if found else "  (no boundary in range)"),
    ]
    if thresh.method == "probabilistic_bisection":
        mass = f"{thresh.credible_mass:.0%}" if thresh.credible_mass else "credible"
        lines += [
            escape(f"{mass} credible interval: [{num(thresh.credible_low)}, {num(thresh.credible_high)}]"),
            f"P(boundary in range): {thresh.probability_boundary_in_range:.2f}   "
            f"P(never fails): {thresh.probability_never_fails:.2f}   "
            f"P(always fails): {thresh.probability_always_fails:.2f}",
            f"Trials:            {thresh.trials}",
        ]
    else:
        lines += [
            f"Safe bound:        {num(thresh.safe_value)}",
            f"Failing bound:     {num(thresh.failure_value)}",
            f"Probed points:     {len(thresh.search_points)} x {thresh.trials or trials} trials",
        ]
    if not found:
        why = {
            "never_fails": f"the command passed across the whole range up to {high}",
            "always_fails": f"the command already failed at {low}",
        }.get(thresh.outcome, "the evidence does not place a boundary inside the range")
        lines.append(f"[yellow]No threshold in range:[/yellow] {why}.")

    console.print(Panel(
        "\n".join(lines),
        title="Threshold Search Result",
        border_style="bold green" if found else "bold yellow",
    ))
    raise typer.Exit(code=EXIT_OK if found else EXIT_NO_BOUNDARY)


@app.command(rich_help_panel=PANEL_RUN)
def minimize(
    command: str | None = typer.Option(None, "--command", "-c", help="Command to execute"),
    project: str | None = typer.Option(None, "--project", help="Connected project id or name"),
    profile: Path | None = typer.Option(
        None, "--profile", "-p",
        help="Target EnvironmentProfile JSON (default: this host plus --latency / --loss)",
    ),
    cwd: str | None = typer.Option(None, "--cwd", help="Working directory for every trial"),
    condition: list[str] | None = typer.Option(
        None, "--condition", help="Condition to consider (repeatable; default: every deviating field)"
    ),
    runs: int = typer.Option(3, "--runs", "-n", min=1, help="Runs per candidate subset"),
    fail_rate: float = typer.Option(
        0.5, "--fail-rate", min=0.0, max=0.999, help="Failure rate above which a subset 'fails'"
    ),
    latency: float = typer.Option(
        defaults.DEMO_LATENCY_MS, "--latency", help="Default target: added latency (ms)"
    ),
    loss: float = typer.Option(
        defaults.DEMO_PACKET_LOSS_PERCENT, "--loss", help="Default target: packet loss (%)"
    ),
    timeout: float = typer.Option(
        defaults.TIMEOUT_SEC, "--timeout", min=0.001, help="Per-trial timeout in seconds"
    ),
    as_json: bool = typer.Option(False, "--json", help="Print the result as JSON only"),
):
    """Find the minimal set of conditions that still reproduces the failure (ddmin)."""
    from morph.api import service

    if not service.HAS_MINIMIZE:
        _fail("this build of morph has no engine.minimize module", as_json=as_json)
    command, cwd = _resolve_project(project, command, cwd, as_json=as_json)
    if profile:
        target = _load_profile(profile, as_json=as_json)
    else:
        target = service.default_target_profile(latency, loss)
    spec = service.MinimizeSpec(
        command=command, target_profile=target, conditions=condition or None, cwd=cwd,
        timeout=timeout, runs=runs, failure_rate_threshold=fail_rate,
    )
    err.print(f"[bold cyan]Minimising the failing condition set ({runs} runs per subset)...[/bold cyan]")
    try:
        outcome = service.run_minimize(spec)
    except service.setup_error_types() as exc:
        _fail(str(exc), as_json=as_json, kind="setup_error")
    except ValueError as exc:
        _fail(str(exc), as_json=as_json)

    if as_json:
        _emit_json(outcome.to_dict())
    else:
        table = Table(title="Subsets tried")
        table.add_column("#", justify="right")
        table.add_column("Conditions", style="cyan")
        table.add_column("Fails")
        for i, entry in enumerate(outcome.history, 1):
            table.add_row(
                str(i), ", ".join(entry["conditions"]) or "(none)",
                "[red]yes[/red]" if entry["fails"] else "[green]no[/green]",
            )
        console.print(table)
        console.print(Panel(
            (f"[bold]{', '.join(outcome.minimal)}[/bold]\n" if outcome.reproduced else "")
            + outcome.summary,
            title="Minimal failing condition set" if outcome.reproduced else "Not reproduced",
            border_style="bold red" if outcome.reproduced else "bold yellow",
        ))
    raise typer.Exit(code=EXIT_OK if outcome.reproduced else EXIT_FAILURE)


@app.command(rich_help_panel=PANEL_RUN)
def cloud(
    profile: Path | None = typer.Option(
        None, "--profile", "-p", help="Profile to assess against this host"
    ),
):
    """Check the remote worker, and whether a profile even needs one."""
    from morph.cloud import assess_locally
    from morph.cloud.worker import RemoteWorker
    from morph.config import load_config

    if profile:
        cap = assess_locally(_load_profile(profile))
        if cap.reproducible_locally:
            console.print("[bold green]Reproducible locally[/bold green] - no worker needed.")
        else:
            table = Table(title="This host falls short of the profile")
            table.add_column("Resource")
            table.add_column("Requested")
            table.add_column("This host")
            table.add_column("Why it needs another machine")
            for short in cap.shortfalls:
                table.add_row(
                    short.field_path, str(short.requested), str(short.available), short.detail
                )
            console.print(table)
            console.print("[yellow]NOT_REPRODUCIBLE_LOCALLY[/yellow] - this run needs a worker.")

    # morph.yaml supplies the worker; MORPH_CLOUD_* still overrides it, so a
    # committed config need not carry the host or the key.
    worker = RemoteWorker(load_config().cloud)
    console.print()
    if not worker.configured:
        console.print(
            "[dim]No worker configured. Set cloud.host in morph.yaml, or the "
            "MORPH_CLOUD_HOST / MORPH_CLOUD_USER / MORPH_CLOUD_SSH_KEY variables.[/dim]"
        )
        raise typer.Exit(code=EXIT_OK)
    if os.environ.get("MORPH_NO_NETWORK"):
        _fail("MORPH_NO_NETWORK is set: refusing to probe the worker")

    err.print(f"[cyan]Probing[/cyan] {worker.target} ...")
    info = worker.check()

    def mark(ok: bool) -> str:
        return "[green]yes[/green]" if ok else "[red]no[/red]"

    lines = [
        f"Reachable:       {mark(info.reachable)}",
        f"Python:          {info.python_version or '-'}",
        f"Morph installed: {mark(info.morph_importable)}",
        f"Can shape net:   {mark(info.can_shape_network)}",
    ]
    if info.detail:
        lines += ["", info.detail]
    console.print(
        Panel("\n".join(lines), title="Cloud worker", border_style="green" if info.usable else "red")
    )
    raise typer.Exit(code=EXIT_OK if info.usable else EXIT_FAILURE)


# --------------------------------------------------------------------------- #
# regressions
# --------------------------------------------------------------------------- #


@app.command(rich_help_panel=PANEL_REG)
def save(
    regression_id: str = typer.Option(..., "--id", help="Regression bundle id (directory name)"),
    profile: Path = typer.Option(..., "--profile", "-p", help="EnvironmentProfile JSON to freeze"),
    command: str = typer.Option(..., "--command", "-c", help="Command the bundle replays"),
    expected_exit: int = typer.Option(0, "--expected-exit", help="Exit code a healthy run returns"),
    max_failure_rate: float = typer.Option(
        0.0, "--max-failure-rate", min=0.0, max=1.0, help="Failure rate a replay may not exceed"
    ),
    failure_signature: str | None = typer.Option(
        None, "--signature", help="Short note on how the failure presents"
    ),
    base_dir: Path = typer.Option(
        Path(".morph/regressions"), "--dir", help="Where to write the bundle"
    ),
):
    """Freeze a profile + command as a replayable regression bundle."""
    from morph.api.validation import validate_id
    from morph.regression import save_regression
    from morph.schema.regression import RegressionArtifact

    try:
        validate_id(regression_id, what="regression id")
    except ValueError as exc:
        _fail(str(exc))
    env = _load_profile(profile)
    artifact = RegressionArtifact(
        regression_id=regression_id,
        environment=env,
        command=command,
        expected_exit_code=expected_exit,
        expected_max_failure_rate=max_failure_rate,
        failure_signature=failure_signature,
    )
    out = save_regression(artifact, base_dir=base_dir)
    console.print(f"[bold green]Saved regression bundle:[/bold green] {out}")
    console.print(f"  replay:  morph replay {regression_id}")
    console.print(f"  export:  morph export {regression_id} -o test_{regression_id}.py")


@app.command(rich_help_panel=PANEL_REG)
def replay(
    regression_path: str = typer.Argument(..., help="Path to regression bundle or regression ID"),
    trials: int = typer.Option(1, "--trials", "-n", min=1, help="Number of replay trials to execute"),
    timeout: float = typer.Option(
        defaults.TIMEOUT_SEC, "--timeout", min=0.001, help="Per-trial timeout in seconds"
    ),
    as_json: bool = typer.Option(False, "--json", help="Print the ReplayResult as JSON only"),
):
    """Replay a recorded regression artifact and verify against expected invariant."""
    from morph.api import service
    from morph.regression import replay_regression

    err.print(f"[bold cyan]Replaying regression:[/bold cyan] {escape(regression_path)}")
    try:
        result = replay_regression(regression_path, trials=trials, timeout=timeout)
    except FileNotFoundError as exc:
        _fail(f"regression bundle not found: {exc}", as_json=as_json, kind="not_found")
    except service.setup_error_types() as exc:
        _fail(str(exc), as_json=as_json, kind="setup_error")
    except ValueError as exc:
        _fail(f"malformed regression bundle: {exc}", as_json=as_json)
    if result.runs and all(service.is_setup_error(r) for r in result.runs):
        _fail(
            service.setup_error_message(result.runs[0], result.regression.command),
            as_json=as_json, kind="setup_error",
        )

    if as_json:
        _emit_json(result)
        raise typer.Exit(code=EXIT_OK if result.matches_expected else EXIT_FAILURE)

    table = Table(title=f"Replay Results: {result.regression_id}")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="magenta")
    table.add_row("Total Trials", str(result.total_runs))
    table.add_row("Failures", str(result.failures))
    table.add_row("Failure Rate", f"{result.failure_rate:.1%}")
    status_str = "[green]COMPLIANT[/green]" if result.matches_expected else "[red]VIOLATION[/red]"
    table.add_row("Invariant Status", status_str)
    console.print(table)
    if not result.matches_expected:
        raise typer.Exit(code=EXIT_FAILURE)


@app.command(name="export", rich_help_panel=PANEL_REG)
def export_cmd(
    regression_path: str = typer.Argument(..., help="Path to regression bundle or regression ID"),
    output: Path = typer.Option("test_morph_invariant.py", "--output", "-o", help="Target test file output"),
):
    """Export a standalone pytest CI invariant test file."""
    from morph.regression import export_ci_test

    try:
        out = export_ci_test(regression_path, output_path=output)
    except FileNotFoundError as exc:
        _fail(f"regression bundle not found: {exc}")
    except ValueError as exc:
        _fail(f"malformed regression bundle: {exc}")
    console.print(f"[bold green]CI test generated successfully:[/bold green] {out}")


# --------------------------------------------------------------------------- #
# interfaces & health
# --------------------------------------------------------------------------- #

_LOOPBACK = {"127.0.0.1", "localhost", "::1"}


@app.command(rich_help_panel=PANEL_UI)
def serve(
    host: str = typer.Option(
        defaults.SERVE_HOST, "--host", "-H",
        help="Bind address. Only loopback by default: the API executes commands and has no auth",
    ),
    port: int = typer.Option(defaults.SERVE_PORT, "--port", "-p", min=1, max=65535, help="Port to listen on"),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload for development"),
    origin: list[str] | None = typer.Option(
        None, "--origin", help="Extra browser origin to allow (repeatable), e.g. http://localhost:3000"
    ),
):
    """Start the Morph API server (backing the React/Vite dashboard)."""
    import uvicorn

    # create_app() reads these when the module-level `app` is built, which is
    # what uvicorn imports (and re-imports under --reload).
    os.environ["MORPH_SERVE_PORT"] = str(port)
    if origin:
        os.environ["MORPH_EXTRA_ORIGINS"] = ",".join(origin)
    if host not in _LOOPBACK:
        os.environ["MORPH_ALLOWED_HOSTS"] = "*"
        err.print(
            Panel(
                f"[bold red]Binding to {host}: the Morph API runs arbitrary commands and has no "
                "authentication.[/bold red]\nAnyone who can reach this port can execute code on this "
                "machine. Only do this on a trusted network.",
                title="WARNING", border_style="red",
            )
        )
    err.print(f"[bold green]Starting Morph API Server at http://{host}:{port}[/bold green]")
    uvicorn.run("morph.api.app:app", host=host, port=port, reload=reload)


@app.command(rich_help_panel=PANEL_UI)
def tui(
    demo: bool = typer.Option(
        False, "--demo", help="Replay a recorded experiment (no root / network / target app needed)"
    ),
):
    """Open the full-screen Morph console: capture, experiment, threshold, replay."""
    from morph.tui import run as run_tui

    run_tui(demo=demo)


@app.command(rich_help_panel=PANEL_UI)
def doctor(
    network: bool = typer.Option(
        True, "--network/--no-network",
        help="Probe the configured worker over SSH (off when MORPH_NO_NETWORK is set)",
    ),
    as_json: bool = typer.Option(False, "--json", help="Print the checks as JSON only"),
):
    """Check this machine: interpreter, adapter, tc/dnctl/cgroups, sudo, proxy, config, worker.

    Exits 1 when any check fails.
    """
    from morph.api import service

    checks = service.doctor(network=network and not os.environ.get("MORPH_NO_NETWORK"))
    failed = [c for c in checks if c.status == "fail"]
    if as_json:
        _emit_json({
            "ok": not failed,
            "checks": [{"name": c.name, "status": c.status, "detail": c.detail} for c in checks],
        })
        raise typer.Exit(code=EXIT_FAILURE if failed else EXIT_OK)

    table = Table(title="morph doctor")
    table.add_column("Check", style="cyan")
    table.add_column("Status")
    table.add_column("Detail", overflow="fold")
    marks = {
        "ok": "[green]ok[/green]",
        "warn": "[yellow]warn[/yellow]",
        "fail": "[bold red]FAIL[/bold red]",
        "skip": "[dim]skip[/dim]",
    }
    for c in checks:
        table.add_row(c.name, marks.get(c.status, c.status), Text(c.detail))
    console.print(table)
    if failed:
        console.print(f"[bold red]{len(failed)} check(s) failed.[/bold red]")
        raise typer.Exit(code=EXIT_FAILURE)
    console.print("[bold green]All checks passed.[/bold green]")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
