"""2D Failure Surface Heatmap engine.

Explores a 2D coordinate grid of environment parameters (e.g. Latency vs Packet Loss)
to map out the safe operational envelope, failure zone, and boundary contour.
"""

from __future__ import annotations

import itertools
from pathlib import Path

from morph.engine.blame import analyze_differential_blame
from morph.engine.runners import set_profile_parameter, with_unconstrained_network
from morph.profiler.capture import capture_environment
from morph.runtime.adapters.base import ProxyAdapter
from morph.runtime.controller import RuntimeController
from morph.schema.blame import DifferentialBlameResult
from morph.schema.profile import EnvironmentProfile
from morph.schema.surface import SafeBoundaryPoint, SurfaceGridPoint, SurfaceRequest, SurfaceResult


def _set_profile_field(profile: EnvironmentProfile, path: str, value: float) -> None:
    parts = path.split(".")
    obj = profile
    for part in parts[:-1]:
        obj = getattr(obj, part, None)
        if obj is None:
            return
    leaf = parts[-1]
    if hasattr(obj, leaf):
        field_obj = getattr(obj, leaf)
        if hasattr(field_obj, "value"):
            field_obj.value = value
            field_obj.status = "captured"
        else:
            setattr(obj, leaf, value)


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


def compute_failure_surface(
    req: SurfaceRequest,
    repo_root: Path | None = None,
) -> SurfaceResult:
    """Execute grid exploration over 2D parameter coordinates and map failure surface."""
    proj_dir = Path(req.project_path)
    if not proj_dir.is_absolute() and repo_root:
        proj_dir = (repo_root / proj_dir).resolve()

    cwd = req.cwd or (str(repo_root) if repo_root and proj_dir.is_relative_to(repo_root) else str(proj_dir))
    cmd = req.command or "py -3 -m apps.timeout test"

    # Compute grid coordinate axes
    if req.x_values:
        x_vals = [float(v) for v in req.x_values]
    else:
        x_min = float(req.x_min if req.x_min is not None else 50.0)
        x_max = float(req.x_max if req.x_max is not None else 300.0)
        x_steps = max(2, int(req.x_steps or 6))
        step_x = (x_max - x_min) / (x_steps - 1)
        x_vals = [round(x_min + i * step_x, 2) for i in range(x_steps)]

    if req.y_values:
        y_vals = [float(v) for v in req.y_values]
    else:
        y_min = float(req.y_min if req.y_min is not None else 0.0)
        y_max = float(req.y_max if req.y_max is not None else 5.0)
        y_steps = max(2, int(req.y_steps or 6))
        step_y = (y_max - y_min) / (y_steps - 1)
        y_vals = [round(y_min + i * step_y, 2) for i in range(y_steps)]

    controller = RuntimeController(adapter=ProxyAdapter())

    # Base profile
    if req.supplied_profile:
        base_profile = EnvironmentProfile.model_validate(req.supplied_profile)
    else:
        try:
            base_profile = capture_environment()
        except Exception:
            base_profile = capture_environment()
    base_profile = with_unconstrained_network(base_profile)

    points_by_coord: dict[tuple[float, float], SurfaceGridPoint] = {}
    passing_points: list[SurfaceGridPoint] = []
    failing_points: list[SurfaceGridPoint] = []

    # Run probes across 2D coordinate grid
    for y, x in itertools.product(y_vals, x_vals):
        trial_prof = set_profile_parameter(base_profile, req.param_x, x)
        trial_prof = set_profile_parameter(trial_prof, req.param_y, y)

        runs = max(1, req.runs_per_point)
        failures = 0
        last_res = None
        for _ in range(runs):
            res = controller.run(
                profile=trial_prof,
                command=cmd,
                cwd=cwd,
            )
            last_res = res
            if not res.passed:
                failures += 1

        passed = failures == 0
        failure_rate = failures / runs
        exit_code = last_res.exit_code if last_res else (0 if passed else 1)
        duration_ms = last_res.duration_ms if last_res else None
        stdout = last_res.stdout if last_res else ""
        stderr = last_res.stderr if last_res else ""

        pt = SurfaceGridPoint(
            x=x,
            y=y,
            passed=passed,
            failure_rate=failure_rate,
            runs=runs,
            exit_code=exit_code,
            duration_ms=duration_ms,
            stdout=stdout,
            stderr=stderr,
        )
        points_by_coord[(x, y)] = pt
        if passed:
            passing_points.append(pt)
        else:
            failing_points.append(pt)

    # Build 2D grid matrix: rows are Y descending, cols are X ascending
    grid_matrix: list[list[SurfaceGridPoint]] = []
    all_points_flat: list[SurfaceGridPoint] = []
    for y in reversed(y_vals):
        row: list[SurfaceGridPoint] = []
        for x in x_vals:
            p = points_by_coord[(x, y)]
            row.append(p)
            all_points_flat.append(p)
        grid_matrix.append(row)

    # Compute boundary points (transition between safe and failing)
    safe_boundary: list[SafeBoundaryPoint] = []
    for x in x_vals:
        # Find maximum Y where test still passed for this X
        passes_at_x = [p for p in passing_points if p.x == x]
        if passes_at_x:
            max_p = max(passes_at_x, key=lambda p: p.y)
            safe_boundary.append(SafeBoundaryPoint(x=max_p.x, y=max_p.y, status="boundary"))

    # Determine highest passing point and lowest failing point
    highest_pass = max(passing_points, key=lambda p: (p.x, p.y)) if passing_points else None
    lowest_fail = min(failing_points, key=lambda p: (p.x, p.y)) if failing_points else None

    # Perform Differential Runtime Blame analysis
    blame: DifferentialBlameResult | None = None
    if highest_pass and lowest_fail:
        _, x_unit = _param_metadata(req.param_x)
        _, y_unit = _param_metadata(req.param_y)
        pass_lbl = f"{highest_pass.x}{x_unit}, {highest_pass.y}{y_unit}"
        fail_lbl = f"{lowest_fail.x}{x_unit}, {lowest_fail.y}{y_unit}"
        blame = analyze_differential_blame(
            pass_output=f"{highest_pass.stdout}\n{highest_pass.stderr}",
            fail_output=f"{lowest_fail.stdout}\n{lowest_fail.stderr}",
            pass_param_label=pass_lbl,
            fail_param_label=fail_lbl,
            project_dir=proj_dir,
        )

    x_lbl, x_unit = _param_metadata(req.param_x)
    y_lbl, y_unit = _param_metadata(req.param_y)

    summary = (
        f"2D Failure Surface mapped over {len(all_points_flat)} coordinate points: "
        f"{len(passing_points)} Safe Operational points, {len(failing_points)} Failure Zone points."
    )

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
