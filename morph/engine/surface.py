"""2D Failure Surface Heatmap engine.

Explores a 2D coordinate grid of environment parameters (e.g. Latency vs Packet
Loss) to map out the safe operational envelope, failure zone, and boundary
contour, then hands the two genuinely *adjacent* cells across the boundary to
the differential blame engine.
"""

from __future__ import annotations

import itertools
from pathlib import Path

from morph.engine.blame import analyze_differential_blame
from morph.engine.runners import set_profile_parameter, with_unconstrained_network
from morph.profiler.capture import capture_environment
from morph.runtime.adapters.base import BaseAdapter, ProxyAdapter
from morph.runtime.controller import RuntimeController, get_default_adapter
from morph.schema.blame import DifferentialBlameResult
from morph.schema.profile import EnvironmentProfile
from morph.schema.surface import SafeBoundaryPoint, SurfaceGridPoint, SurfaceRequest, SurfaceResult


def _param_metadata(param: str) -> tuple[str, str]:
    mapping = {
        "network.latency_ms": ("Network Latency", "ms"),
        "network.packet_loss_percent": ("Packet Loss", "%"),
        "network.jitter_ms": ("Jitter", "ms"),
        "network.bandwidth_mbps": ("Bandwidth", "Mbps"),
        "cpu.quota_percent": ("CPU Quota", "%"),
        "memory.pressure_percent": ("Memory Pressure", "%"),
        "process.timeout_s": ("Process Timeout", "s"),
    }
    return mapping.get(param, (param.replace("_", " ").title(), ""))


def _adapter_for(name: str) -> BaseAdapter:
    """Resolve ``SurfaceRequest.adapter_name`` to a runtime adapter."""
    key = (name or "proxy").strip().lower()
    if key == "proxy":
        return ProxyAdapter()
    if key in {"system", "auto", "default", "host"}:
        return get_default_adapter()
    if key in {"macos", "darwin"}:
        from morph.runtime.adapters.macos import MacOSAdapter
        return MacOSAdapter()
    if key == "linux":
        from morph.runtime.adapters.linux import LinuxAdapter
        return LinuxAdapter()
    if key == "windows":
        from morph.runtime.adapters.windows import WindowsAdapter
        return WindowsAdapter()
    raise ValueError(f"unknown adapter '{name}' (expected proxy, system, macos, linux or windows)")


def _axis(values: list[float] | None, lo: float | None, hi: float | None, steps: int | None,
          default_lo: float, default_hi: float) -> list[float]:
    if values:
        return [float(v) for v in values]
    lo_f = float(lo if lo is not None else default_lo)
    hi_f = float(hi if hi is not None else default_hi)
    n = max(2, int(steps or 6))
    step = (hi_f - lo_f) / (n - 1)
    return [round(lo_f + i * step, 2) for i in range(n)]


def boundary_pair(
    points: dict[tuple[float, float], SurfaceGridPoint],
    x_vals: list[float],
    y_vals: list[float],
) -> tuple[SurfaceGridPoint, SurfaceGridPoint] | None:
    """The adjacent (passing, failing) pair of cells that best marks the boundary.

    Primary sweep: within each x column, the highest-y passing cell and the
    failing cell immediately above it. Fallback sweep: within each y row, the
    highest-x passing cell and the failing cell immediately to its right.
    Among candidates the pair with the largest jump in failure rate wins (ties
    go to the lower coordinates). ``None`` when no passing cell is adjacent to
    a failing one -- e.g. everything passed, or everything failed.
    """
    xs, ys = sorted(x_vals), sorted(y_vals)

    def best(pairs: list[tuple[SurfaceGridPoint, SurfaceGridPoint]]):
        if not pairs:
            return None
        return max(pairs, key=lambda pf: (pf[1].failure_rate - pf[0].failure_rate, -pf[1].y, -pf[1].x))

    column_pairs = []
    for x in xs:
        column = [points[(x, y)] for y in ys if (x, y) in points]
        for lower, upper in itertools.pairwise(column):
            if lower.passed and not upper.passed:
                column_pairs.append((lower, upper))  # highest pass / lowest fail meet here
    chosen = best(column_pairs)
    if chosen is not None:
        return chosen

    row_pairs = []
    for y in ys:
        row = [points[(x, y)] for x in xs if (x, y) in points]
        for left, right in itertools.pairwise(row):
            if left.passed and not right.passed:
                row_pairs.append((left, right))
    return best(row_pairs)


def compute_failure_surface(
    req: SurfaceRequest,
    repo_root: Path | None = None,
    controller: RuntimeController | None = None,
) -> SurfaceResult:
    """Execute grid exploration over 2D parameter coordinates and map the failure surface.

    A cell passes when its failure rate over ``runs_per_point`` runs is at
    most ``req.failure_rate_threshold`` (the threshold search's rule). Blame is
    computed on the adjacent pass/fail pair from :func:`boundary_pair`, never
    on two arbitrary cells.
    """
    if not req.command or not req.command.strip():
        raise ValueError("SurfaceRequest.command is required")
    if not 0.0 <= req.failure_rate_threshold < 1.0:
        raise ValueError("failure_rate_threshold must be in [0, 1)")

    proj_dir = Path(req.project_path)
    if not proj_dir.is_absolute() and repo_root:
        proj_dir = (repo_root / proj_dir).resolve()

    cwd = req.cwd or (str(repo_root) if repo_root and proj_dir.is_relative_to(repo_root) else str(proj_dir))
    cmd = req.command

    x_vals = _axis(req.x_values, req.x_min, req.x_max, req.x_steps, 50.0, 300.0)
    y_vals = _axis(req.y_values, req.y_min, req.y_max, req.y_steps, 0.0, 5.0)

    controller = controller or RuntimeController(adapter=_adapter_for(req.adapter_name))

    if req.supplied_profile:
        base_profile = EnvironmentProfile.model_validate(req.supplied_profile)
    else:
        base_profile = capture_environment()
    base_profile = with_unconstrained_network(base_profile)

    points_by_coord: dict[tuple[float, float], SurfaceGridPoint] = {}
    passing_points: list[SurfaceGridPoint] = []
    failing_points: list[SurfaceGridPoint] = []
    runs = max(1, req.runs_per_point)

    for y, x in itertools.product(y_vals, x_vals):
        trial_prof = set_profile_parameter(base_profile, req.param_x, x)
        trial_prof = set_profile_parameter(trial_prof, req.param_y, y)

        failures = 0
        last_failing = None
        last_res = None
        for _ in range(runs):
            res = controller.run(profile=trial_prof, command=cmd, cwd=cwd, timeout=req.timeout)
            last_res = res
            if not res.passed:
                failures += 1
                last_failing = res

        failure_rate = failures / runs
        passed = failure_rate <= req.failure_rate_threshold
        # Show the output that explains the cell's verdict: a failing run when
        # the cell failed, otherwise the last run.
        shown = last_failing if (not passed and last_failing is not None) else last_res

        pt = SurfaceGridPoint(
            x=x,
            y=y,
            passed=passed,
            failure_rate=failure_rate,
            runs=runs,
            exit_code=shown.exit_code,
            duration_ms=shown.duration_ms,
            stdout=shown.stdout,
            stderr=shown.stderr,
        )
        points_by_coord[(x, y)] = pt
        (passing_points if passed else failing_points).append(pt)

    # Build 2D grid matrix: rows are Y descending, cols are X ascending
    grid_matrix: list[list[SurfaceGridPoint]] = []
    all_points_flat: list[SurfaceGridPoint] = []
    for y in reversed(y_vals):
        row = [points_by_coord[(x, y)] for x in x_vals]
        grid_matrix.append(row)
        all_points_flat.extend(row)

    # Boundary contour: for each x, the maximum y that still passes
    safe_boundary: list[SafeBoundaryPoint] = []
    for x in x_vals:
        passes_at_x = [p for p in passing_points if p.x == x]
        if passes_at_x:
            max_p = max(passes_at_x, key=lambda p: p.y)
            safe_boundary.append(SafeBoundaryPoint(x=max_p.x, y=max_p.y, status="boundary"))

    pair = boundary_pair(points_by_coord, x_vals, y_vals)
    highest_pass, lowest_fail = pair if pair else (None, None)

    blame: DifferentialBlameResult | None = None
    x_lbl, x_unit = _param_metadata(req.param_x)
    y_lbl, y_unit = _param_metadata(req.param_y)
    if highest_pass and lowest_fail:
        blame = analyze_differential_blame(
            pass_output=f"{highest_pass.stdout or ''}\n{highest_pass.stderr or ''}",
            fail_output=f"{lowest_fail.stdout or ''}\n{lowest_fail.stderr or ''}",
            pass_param_label=f"{highest_pass.x}{x_unit}, {highest_pass.y}{y_unit}",
            fail_param_label=f"{lowest_fail.x}{x_unit}, {lowest_fail.y}{y_unit}",
            project_dir=proj_dir,
        )

    summary = (
        f"2D failure surface mapped over {len(all_points_flat)} coordinate points: "
        f"{len(passing_points)} safe, {len(failing_points)} failing "
        f"(a point fails when its failure rate over {runs} run(s) exceeds {req.failure_rate_threshold:g})."
    )
    if pair is None:
        summary += " No passing cell is adjacent to a failing one, so no boundary pair was blamed."

    return SurfaceResult(
        param_x=req.param_x,
        param_y=req.param_y,
        param_x_label=x_lbl,
        param_y_label=y_lbl,
        param_x_unit=x_unit,
        param_y_unit=y_unit,
        x_values=x_vals,
        y_values=y_vals,
        grid=grid_matrix,
        points=all_points_flat,
        safe_boundary=safe_boundary,
        passing_count=len(passing_points),
        failing_count=len(failing_points),
        total_points=len(all_points_flat),
        highest_passing_point=highest_pass,
        lowest_failing_point=lowest_fail,
        blame=blame,
        summary=summary,
    )
