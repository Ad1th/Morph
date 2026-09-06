"""Typer CLI interface for Morph."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer
import uvicorn
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from morph.profiler.capture import capture_environment
from morph.regression import export_ci_test, load_regression, replay_regression
from morph.runtime.controller import RuntimeController
from morph.schema.profile import EnvironmentProfile

app = typer.Typer(name="morph", help="Morph: Test software in environments you don't physically have.")
console = Console()


@app.command()
def capture(
    output: Optional[Path] = typer.Option(
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
    template: str = typer.Option("default", "--template", "-t", help="Template type (default, high-latency, constrained)"),
):
    """Generate a template environment profile JSON for editing."""
    base = capture_environment()
    if template == "high-latency" and base.network:
        base.network.latency_ms.value = 200.0
        base.network.packet_loss_percent.value = 2.0
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
    command: str = typer.Option(..., "--command", "-c", help="Command to execute"),
    profile: Optional[Path] = typer.Option(None, "--profile", "-p", help="Path to EnvironmentProfile JSON"),
    timeout: float = typer.Option(30.0, "--timeout", help="Timeout in seconds"),
    force_proxy: bool = typer.Option(False, "--force-proxy", help="Force user-space TCP proxy instead of native OS tools"),
):
    """Run an application under a simulated environment profile."""
    controller = RuntimeController(force_proxy=force_proxy)

    env_profile = None
    if profile:
        if not profile.exists():
            console.print(f"[bold red]Error:[/bold red] Profile file '{profile}' not found")
            raise typer.Exit(code=1)
        env_profile = EnvironmentProfile.model_validate_json(profile.read_text(encoding="utf-8"))

    console.print(f"[cyan]Executing:[/cyan] {command}")
    if env_profile:
        result = controller.run(profile=env_profile, command=command, timeout=timeout)
    else:
        from morph.runtime.runner import execute_command
        result = execute_command(command=command, timeout=timeout)

    status_style = "bold green" if result.passed else "bold red"
    console.print(Panel(
        f"Exit Code: {result.exit_code}\n"
        f"Duration: {result.duration_ms:.1f}ms\n"
        f"Peak Memory: {result.peak_memory_mb:.1f} MB\n"
        f"Passed: {result.passed}" + (f"\nError: {result.error_type}: {result.error_message}" if not result.passed else ""),
        title=f"Run Result — [{'PASS' if result.passed else 'FAIL'}]",
        border_style=status_style,
    ))

    if result.stdout:
        console.print(f"[bold]STDOUT:[/bold]\n{result.stdout.strip()}")
    if result.stderr:
        console.print(f"[bold red]STDERR:[/bold red]\n{result.stderr.strip()}")

    if not result.passed:
        raise typer.Exit(code=result.exit_code or 1)


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
    table.add_row("Expected Max Rate", f"{result.regression.expected_max_failure_rate:.1%}")
    table.add_row("Invariant Status", "[green]COMPLIANT[/green]" if result.matches_expected else "[red]VIOLATION[/red]")

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


if __name__ == "__main__":
    app()
