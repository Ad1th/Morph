"""Typer CLI interface for Morph."""

from __future__ import annotations

import json
from pathlib import Path

import typer
import uvicorn
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from morph.engine.experiment import run_experiment
from morph.engine.runners import (
    make_threshold_run_fn,
    set_profile_parameter,
    with_unconstrained_network,
)
from morph.engine.threshold import search_threshold
from morph.profiler.capture import capture_environment
from morph.regression import export_ci_test, replay_regression, save_regression
from morph.runtime.controller import RuntimeController
from morph.schema.profile import EnvironmentProfile, FieldStatus, NetworkInfo, ProfileField
from morph.schema.regression import RegressionArtifact

app = typer.Typer(name="morph", help="Morph: Test software in environments you don't physically have.")
console = Console()



# --------------------------------------------------------------------------- #
# projects: `morph connect` a repo/dir once, then `--project <id>` everywhere
# --------------------------------------------------------------------------- #


def _resolve_project(
    project: str | None, command: str | None, cwd: str | None
) -> tuple[str, str | None]:
    """Fill in `command` / `cwd` from a registered project when `--project` is
    given. An explicit `--command` still wins. Returns (command, cwd)."""
    if project:
        from morph import projects as _projects

        try:
            proj = _projects.load(project)
        except KeyError as exc:
            console.print(f"[bold red]Error:[/bold red] {exc}")
            raise typer.Exit(code=1)
        command = command or proj.command
        cwd = cwd or proj.cwd
        if not command:
            console.print(
                f"[bold red]Error:[/bold red] project '{proj.name}' has no detected command; "
                "pass --command"
            )
            raise typer.Exit(code=1)
    if not command:
        console.print("[bold red]Error:[/bold red] one of --command or --project is required")
        raise typer.Exit(code=1)
    return command, cwd


@app.command()
def connect(
    source: str = typer.Argument(..., help="owner/repo, a GitHub URL, or a local directory path"),
    branch: str | None = typer.Option(None, "--branch", "-b", help="Branch to clone"),
    token: str | None = typer.Option(None, "--token", help="GitHub token (else gh CLI / env)"),
    install: bool = typer.Option(
        False, "--install", help="Create an isolated venv and install the project's dependencies"
    ),
    name: str | None = typer.Option(None, "--name", help="Registry name (default: repo/dir name)"),
):
    """Add a GitHub repo or local directory as a runnable project."""
    from morph import github, project_setup

    console.print(f"[cyan]Connecting[/cyan] {source} …  [dim](auth: {github.token_source(token)})[/dim]")
    try:
        proj = project_setup.connect(
            source, token=token, branch=branch, install=install, name=name,
            logger=lambda m: console.print(f"  [dim]{m}[/dim]"),
        )
    except (github.GitHubError, FileNotFoundError) as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(code=1)

    table = Table(title=f"Connected: {proj.name}", show_header=False)
    table.add_column(style="cyan")
    table.add_column(style="white")
    table.add_row("id", proj.id)
    table.add_row("source", proj.source + (f"  ({proj.repo}@{proj.commit})" if proj.repo else ""))
    table.add_row("path", proj.path)
    table.add_row("command", proj.command or "[yellow]not detected — pass --command[/yellow]")
    if proj.venv:
        table.add_row("venv", proj.venv)
    table.add_row("files", str(proj.file_count))
    console.print(table)
    console.print(f"\n[green]next:[/green]  morph experiment --project {proj.id}")


@app.command()
def projects(
    remove: str | None = typer.Option(None, "--rm", help="Delete a project by id or name"),
):
    """List connected projects (or --rm one)."""
    from morph import projects as _projects

    if remove:
        ok = _projects.delete(remove)
        console.print(f"[green]removed[/green] {remove}" if ok else f"[yellow]no such:[/yellow] {remove}")
        return

    rows = _projects.list_projects()
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



@app.command()
def capture(
    output: Path | None = typer.Option(
        None, "--output", "-o", help="Path to save captured profile JSON"
    )
):
    """Capture the physical environment of the current machine."""
    console.print("[bold cyan]Capturing host environment...[/bold cyan]")
    profile = capture_environment()
    json_str = profile.model_dump_json(indent=2)

    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json_str, encoding="utf-8")
        console.print(f"[bold green]Profile saved to:[/bold green] {output}")
    else:
        console.print_json(json_str)


@app.command()
def define(
    output: Path = typer.Option("target_profile.json", "--output", "-o", help="Target output file"),
    template: str = typer.Option(
        "default", "--template", "-t", help="Template type (default, high-latency, constrained)"
    ),
):
    """Generate a template environment profile JSON for editing."""
    base = capture_environment()
    if template == "high-latency":
        # capture_environment() does not populate `network` (no local network
        # collector), so synthesize the section the template is meant to request.
        if base.network is None:
            base.network = NetworkInfo(
                latency_ms=ProfileField(value=0.0, status=FieldStatus.REQUESTED),
                packet_loss_percent=ProfileField(value=0.0, status=FieldStatus.REQUESTED),
            )
        # 120 ms / 18 % is the validated operating point for the flagship
        # interaction fixture (apps/pool_retry): neither condition alone moves
        # the failure rate, the pair drives it to ~100 %. See apps/README.md.
        base.network.latency_ms.value = 120.0
        base.network.latency_ms.status = FieldStatus.REQUESTED
        base.network.packet_loss_percent.value = 18.0
        base.network.packet_loss_percent.status = FieldStatus.REQUESTED
    elif template == "constrained":
        if base.cpu and base.cpu.cores:
            base.cpu.cores.value = 2
        if base.memory and base.memory.total_mb:
            base.memory.total_mb.value = 4096

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(base.model_dump_json(indent=2), encoding="utf-8")
    console.print(f"[bold green]Template profile ({template}) written to:[/bold green] {output}")


@app.command()
def run(
    command: str | None = typer.Option(None, "--command", "-c", help="Command to execute"),
    project: str | None = typer.Option(None, "--project", help="Connected project id or name"),
    profile: Path | None = typer.Option(None, "--profile", "-p", help="Path to EnvironmentProfile JSON"),
    cwd: str | None = typer.Option(None, "--cwd", help="Working directory for the command"),
    timeout: float = typer.Option(30.0, "--timeout", help="Timeout in seconds"),
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
    """Run an application under a simulated environment profile."""
    command, cwd = _resolve_project(project, command, cwd)
    controller = RuntimeController(force_proxy=force_proxy)

    env_profile = None
    if profile:
        if not profile.exists():
            console.print(f"[bold red]Error:[/bold red] Profile file '{profile}' not found")
            raise typer.Exit(code=1)
        env_profile = EnvironmentProfile.model_validate_json(profile.read_text(encoding="utf-8"))

    if not as_json:
        console.print(
            f"[cyan]Executing:[/cyan] {command}" + (f"  [dim](cwd: {cwd})[/dim]" if cwd else "")
        )

    placement = None
    if env_profile and cloud:
        from morph.cloud import NotReproducibleAnywhere, run_anywhere

        try:
            result, placement = run_anywhere(
                profile=env_profile, command=command, timeout=timeout,
                controller=controller, cwd=cwd,
            )
        except NotReproducibleAnywhere as exc:
            if as_json:
                print(json.dumps({"error": "not_reproducible", "detail": str(exc)}))
            else:
                console.print(f"[bold red]{exc}[/bold red]")
            raise typer.Exit(code=2) from exc
    elif env_profile:
        result = controller.run(profile=env_profile, command=command, timeout=timeout, cwd=cwd)
    else:
        from morph.runtime.runner import execute_command
        result = execute_command(command=command, timeout=timeout, cwd=cwd)

    # Machine mode: a bare JSON document on stdout and nothing else. This is
    # the contract morph.cloud.worker parses when Morph runs on another box.
    if as_json:
        print(result.model_dump_json())
        raise typer.Exit(code=0 if result.passed else 1)

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

    if result.stdout:
        console.print(f"[bold]STDOUT:[/bold]\n{result.stdout.strip()}")
    if result.stderr:
        console.print(f"[bold red]STDERR:[/bold red]\n{result.stderr.strip()}")

    if not result.passed:
        raise typer.Exit(code=result.exit_code or 1)


@app.command()
def experiment(
    command: str | None = typer.Option(None, "--command", "-c", help="Command to execute"),
    project: str | None = typer.Option(None, "--project", help="Connected project id or name"),
    profile: Path | None = typer.Option(
        None, "--profile", "-p", help="Target EnvironmentProfile JSON (default: host + latency/loss)"
    ),
    cwd: str | None = typer.Option(None, "--cwd", help="Working directory for every trial"),
    trials: int = typer.Option(5, "--trials", "-n", help="Number of trials per condition"),
    timeout: float = typer.Option(30.0, "--timeout", help="Per-trial timeout in seconds"),
):
    """Run an automated causal isolation experiment across baseline and candidate treatments."""
    command, cwd = _resolve_project(project, command, cwd)

    if profile is not None:
        if not profile.exists():
            console.print(f"[bold red]Error:[/bold red] Profile file '{profile}' not found")
            raise typer.Exit(code=1)
        target = EnvironmentProfile.model_validate_json(profile.read_text(encoding="utf-8"))
    else:
        target = capture_environment()
        target.network = NetworkInfo(
            latency_ms=ProfileField(value=120.0, status=FieldStatus.REQUESTED),
            packet_loss_percent=ProfileField(value=18.0, status=FieldStatus.REQUESTED),
        )

    controller = RuntimeController()

    def _make_runner(p=None):
        def _runner() -> bool:
            if p is not None:
                res = controller.run(profile=p, command=command, timeout=timeout, cwd=cwd)
            else:
                from morph.runtime.runner import execute_command
                res = execute_command(command=command, timeout=timeout, cwd=cwd)
            return res.passed
        return _runner

    # Build candidates
    candidates = {}
    if target.network and float(target.network.latency_ms.value or 0.0) > 0:
        lat_profile = target.model_copy(deep=True)
        lat_profile.network.packet_loss_percent.value = 0.0
        candidates["latency_only"] = _make_runner(lat_profile)

    if target.network and float(target.network.packet_loss_percent.value or 0.0) > 0:
        loss_profile = target.model_copy(deep=True)
        loss_profile.network.latency_ms.value = 0.0
        candidates["loss_only"] = _make_runner(loss_profile)

    candidates["full_target"] = _make_runner(target)

    console.print(f"[bold cyan]Running causal experiment ({trials} trials per condition)...[/bold cyan]")
    exp_res = run_experiment(
        baseline_run_fn=_make_runner(None),
        candidates=candidates,
        n=trials,
    )

    table = Table(title="Causal Isolation Results")
    table.add_column("Condition", style="cyan")
    table.add_column("Failures", style="magenta")
    table.add_column("Failure Rate", style="yellow")
    table.add_column("P-Value", style="blue")
    table.add_column("Effect", style="green")

    if exp_res.baseline:
        table.add_row(
            "baseline",
            f"{exp_res.baseline.failures}/{exp_res.baseline.total_runs}",
            f"{exp_res.baseline.failure_rate:.1%}",
            "-",
            "control",
        )

    for cmp in exp_res.comparisons:
        table.add_row(
            cmp.condition_label,
            f"{cmp.treatment_failures}/{cmp.treatment_total}",
            f"{cmp.treatment_failure_rate:.1%}",
            f"{cmp.p_value:.4f}" if cmp.p_value is not None else "-",
            cmp.effect_label,
        )

    console.print(table)
    console.print(f"\n[bold]Classification:[/bold] [yellow]{exp_res.classification}[/yellow]")
    console.print(f"[bold]Summary:[/bold] {exp_res.summary}")


@app.command()
def threshold(
    command: str | None = typer.Option(None, "--command", "-c", help="Command to execute"),
    project: str | None = typer.Option(None, "--project", help="Connected project id or name"),
    profile: Path | None = typer.Option(
        None, "--profile", "-p", help="Base EnvironmentProfile JSON (default: captured host)"
    ),
    cwd: str | None = typer.Option(None, "--cwd", help="Working directory for every trial"),
    parameter: str = typer.Option(..., "--parameter", help="Parameter to search (e.g. network.latency_ms)"),
    low: float = typer.Option(0.0, "--low", help="Lower bound value"),
    high: float = typer.Option(500.0, "--high", help="Upper bound value"),
    trials: int = typer.Option(3, "--trials", "-n", help="Trials per probe point"),
    timeout: float = typer.Option(30.0, "--timeout", help="Per-trial timeout in seconds"),
):
    """Search for the failure tipping point of a specific environmental parameter."""
    command, cwd = _resolve_project(project, command, cwd)

    if profile is not None:
        if not profile.exists():
            console.print(f"[bold red]Error:[/bold red] Profile file '{profile}' not found")
            raise typer.Exit(code=1)
        base = EnvironmentProfile.model_validate_json(profile.read_text(encoding="utf-8"))
    else:
        base = capture_environment()

    # Same runner the API's /threshold route uses, so both entry points apply
    # the parameter identically instead of the CLI silently ignoring it when
    # the saved profile has no network section.
    try:
        run_at = make_threshold_run_fn(
            command=command, profile=base, parameter=parameter, timeout=timeout, cwd=cwd
        )
        set_profile_parameter(with_unconstrained_network(base), parameter, low)
    except ValueError as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(code=1)

    console.print(f"[bold cyan]Searching threshold for '{parameter}' between [{low}, {high}]...[/bold cyan]")
    thresh = search_threshold(
        parameter=parameter,
        run_at=run_at,
        low=low,
        high=high,
        trials=trials,
    )

    safe_str = f"{thresh.safe_value:.2f}" if thresh.safe_value is not None else "None"
    fail_str = f"{thresh.failure_value:.2f}" if thresh.failure_value is not None else "None"
    est_str = (
        f"{thresh.boundary_estimate:.2f}"
        if thresh.boundary_estimate is not None
        else "None (no threshold in range)"
    )

    console.print(Panel(
        f"Parameter: {thresh.parameter}\n"
        f"Safe Bound: {safe_str}\n"
        f"Failing Bound: {fail_str}\n"
        f"Boundary Estimate: {est_str}\n"
        f"Probed Points: {len(thresh.search_points)}",
        title="Threshold Search Result",
        border_style="bold green",
    ))



@app.command()
def save(
    regression_id: str = typer.Option(..., "--id", help="Regression bundle id (directory name)"),
    profile: Path = typer.Option(..., "--profile", "-p", help="EnvironmentProfile JSON to freeze"),
    command: str = typer.Option(..., "--command", "-c", help="Command the bundle replays"),
    expected_exit: int = typer.Option(0, "--expected-exit", help="Exit code a healthy run returns"),
    max_failure_rate: float = typer.Option(
        0.0, "--max-failure-rate", help="Failure rate a replay may not exceed"
    ),
    failure_signature: str | None = typer.Option(
        None, "--signature", help="Short note on how the failure presents"
    ),
    base_dir: Path = typer.Option(
        Path(".morph/regressions"), "--dir", help="Where to write the bundle"
    ),
):
    """Freeze a profile + command as a replayable regression bundle."""
    if not profile.exists():
        console.print(f"[bold red]Error:[/bold red] Profile file '{profile}' not found")
        raise typer.Exit(code=1)

    env = EnvironmentProfile.model_validate_json(profile.read_text(encoding="utf-8"))
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


@app.command()
def replay(
    regression_path: str = typer.Argument(..., help="Path to regression bundle or regression ID"),
    trials: int = typer.Option(1, "--trials", "-n", help="Number of replay trials to execute"),
    timeout: float = typer.Option(30.0, "--timeout", help="Per-trial timeout in seconds"),
):
    """Replay a recorded regression artifact and verify against expected invariant."""
    console.print(f"[bold cyan]Replaying regression:[/bold cyan] {regression_path}")
    result = replay_regression(regression_path, trials=trials, timeout=timeout)

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
        raise typer.Exit(code=1)


@app.command(name="export")
def export_cmd(
    regression_path: str = typer.Argument(..., help="Path to regression bundle or regression ID"),
    output: Path = typer.Option("test_morph_invariant.py", "--output", "-o", help="Target test file output"),
):
    """Export a standalone pytest CI invariant test file."""
    out = export_ci_test(regression_path, output_path=output)
    console.print(f"[bold green]CI test generated successfully:[/bold green] {out}")


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Host address to bind"),
    port: int = typer.Option(8000, "--port", "-p", help="Port to listen on"),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload for development"),
):
    """Start the Morph API server (backing the React/Vite dashboard)."""
    console.print(f"[bold green]Starting Morph API Server at http://{host}:{port}[/bold green]")
    uvicorn.run("morph.api.app:app", host=host, port=port, reload=reload)


@app.command()
def tui(
    demo: bool = typer.Option(
        False, "--demo", help="Replay a recorded experiment (no root / network / target app needed)"
    ),
):
    """Open the full-screen Morph console: capture, experiment, threshold, replay."""
    from morph.tui import run

    run(demo=demo)


@app.command()
def cloud(
    profile: Path | None = typer.Option(
        None, "--profile", "-p", help="Profile to assess against this host"
    ),
):
    """Check the remote worker, and whether a profile even needs one."""
    from morph.cloud import assess_locally
    from morph.cloud.worker import RemoteWorker

    if profile:
        if not profile.exists():
            console.print(f"[bold red]Error:[/bold red] Profile file '{profile}' not found")
            raise typer.Exit(code=1)
        cap = assess_locally(
            EnvironmentProfile.model_validate_json(profile.read_text(encoding="utf-8"))
        )
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

    worker = RemoteWorker()
    console.print()
    if not worker.configured:
        console.print(
            "[dim]No worker configured. Set cloud.host in morph.yaml, or the "
            "MORPH_CLOUD_HOST / MORPH_CLOUD_USER / MORPH_CLOUD_SSH_KEY variables.[/dim]"
        )
        raise typer.Exit(code=0)

    console.print(f"[cyan]Probing[/cyan] {worker.target} ...")
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
        Panel(
            "\n".join(lines),
            title="Cloud worker",
            border_style="green" if info.usable else "red",
        )
    )
    raise typer.Exit(code=0 if info.usable else 1)


if __name__ == "__main__":
    app()
