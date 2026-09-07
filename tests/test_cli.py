from typer.testing import CliRunner

from morph.cli.main import app

runner = CliRunner()


def test_cli_capture(tmp_path):
    out_file = tmp_path / "captured.json"
    result = runner.invoke(app, ["capture", "--output", str(out_file)])
    assert result.exit_code == 0
    assert out_file.exists()


def test_cli_define(tmp_path):
    out_file = tmp_path / "custom_profile.json"
    result = runner.invoke(app, ["define", "--output", str(out_file), "--template", "high-latency"])
    assert result.exit_code == 0
    assert out_file.exists()


def test_cli_run_command():
    result = runner.invoke(app, ["run", "--command", "python3 -c \"print('cli test')\""])
    assert result.exit_code == 0
    assert "cli test" in result.stdout


def test_cli_export_and_replay(tmp_path, monkeypatch):
    import morph.regression.artifact
    from morph.regression import save_regression
    from morph.schema.profile import (
        CPUInfo,
        EnvironmentProfile,
        FieldStatus,
        LocaleInfo,
        MemoryInfo,
        NetworkInfo,
        OSInfo,
        ProfileField,
    )
    from morph.schema.regression import RegressionArtifact

    monkeypatch.setattr(morph.regression.artifact, "DEFAULT_REGRESSIONS_DIR", tmp_path)

    profile = EnvironmentProfile(
        version="1.0",
        os=OSInfo(
            family=ProfileField(value="darwin", status=FieldStatus.CAPTURED),
            version=ProfileField(value="14.5", status=FieldStatus.CAPTURED),
        ),
        cpu=CPUInfo(
            architecture=ProfileField(value="arm64", status=FieldStatus.CAPTURED),
            cores=ProfileField(value=8, status=FieldStatus.CAPTURED),
            logical_processors=ProfileField(value=8, status=FieldStatus.CAPTURED),
        ),
        memory=MemoryInfo(total_mb=ProfileField(value=16384, status=FieldStatus.CAPTURED)),
        locale=LocaleInfo(
            locale=ProfileField(value="en_US.UTF-8", status=FieldStatus.CAPTURED),
            timezone=ProfileField(value="UTC", status=FieldStatus.CAPTURED),
        ),
        network=NetworkInfo(
            latency_ms=ProfileField(value=10.0, status=FieldStatus.REQUESTED),
            packet_loss_percent=ProfileField(value=0.0, status=FieldStatus.REQUESTED),
        ),
    )
    artifact = RegressionArtifact(
        regression_id="cli-reg-001",
        environment=profile,
        command="python3 -c \"print('cli replay ok')\"",
        expected_exit_code=0,
    )
    saved_path = save_regression(artifact, base_dir=tmp_path)

    # Replay CLI
    replay_res = runner.invoke(app, ["replay", str(saved_path), "--trials", "1"])
    assert replay_res.exit_code == 0

    # Export CLI
    out_ci = tmp_path / "ci_test.py"
    export_res = runner.invoke(app, ["export", str(saved_path), "--output", str(out_ci)])
    assert export_res.exit_code == 0
    assert out_ci.exists()


def test_cli_save_then_replay(tmp_path):
    profile = tmp_path / "target.json"
    runner.invoke(app, ["capture", "--output", str(profile)])
    bundles = tmp_path / "bundles"

    result = runner.invoke(
        app,
        [
            "save",
            "--id", "cli-save-001",
            "--profile", str(profile),
            "--command", "python3 -c \"print('saved ok')\"",
            "--max-failure-rate", "0.0",
            "--dir", str(bundles),
        ],
    )
    assert result.exit_code == 0
    bundle = bundles / "cli-save-001"
    assert (bundle / "environment.json").exists()
    assert (bundle / "command.json").exists()

    replay_res = runner.invoke(app, ["replay", str(bundle), "--trials", "1"])
    assert replay_res.exit_code == 0


def test_cli_experiment(tmp_path):
    from morph.schema.profile import (
        CPUInfo,
        EnvironmentProfile,
        FieldStatus,
        LocaleInfo,
        MemoryInfo,
        NetworkInfo,
        OSInfo,
        ProfileField,
    )
    profile = EnvironmentProfile(
        version="1.0",
        os=OSInfo(
            family=ProfileField(value="darwin", status=FieldStatus.CAPTURED),
            version=ProfileField(value="14.5", status=FieldStatus.CAPTURED),
        ),
        cpu=CPUInfo(
            architecture=ProfileField(value="arm64", status=FieldStatus.CAPTURED),
            cores=ProfileField(value=8, status=FieldStatus.CAPTURED),
            logical_processors=ProfileField(value=8, status=FieldStatus.CAPTURED),
        ),
        memory=MemoryInfo(total_mb=ProfileField(value=16384, status=FieldStatus.CAPTURED)),
        locale=LocaleInfo(
            locale=ProfileField(value="en_US.UTF-8", status=FieldStatus.CAPTURED),
            timezone=ProfileField(value="UTC", status=FieldStatus.CAPTURED),
        ),
        network=NetworkInfo(
            latency_ms=ProfileField(value=10.0, status=FieldStatus.REQUESTED),
            packet_loss_percent=ProfileField(value=0.0, status=FieldStatus.REQUESTED),
        ),
    )
    p_file = tmp_path / "target_prof.json"
    p_file.write_text(profile.model_dump_json(), encoding="utf-8")

    res = runner.invoke(
        app,
        [
            "experiment",
            "--profile",
            str(p_file),
            "--command",
            "python3 -c \"print('exp test')\"",
            "--trials",
            "1",
        ],
    )
    assert res.exit_code == 0

    assert "Causal Isolation Results" in res.stdout


def test_cli_threshold(tmp_path):
    from morph.schema.profile import (
        CPUInfo,
        EnvironmentProfile,
        FieldStatus,
        LocaleInfo,
        MemoryInfo,
        NetworkInfo,
        OSInfo,
        ProfileField,
    )
    profile = EnvironmentProfile(
        version="1.0",
        os=OSInfo(
            family=ProfileField(value="darwin", status=FieldStatus.CAPTURED),
            version=ProfileField(value="14.5", status=FieldStatus.CAPTURED),
        ),
        cpu=CPUInfo(
            architecture=ProfileField(value="arm64", status=FieldStatus.CAPTURED),
            cores=ProfileField(value=8, status=FieldStatus.CAPTURED),
            logical_processors=ProfileField(value=8, status=FieldStatus.CAPTURED),
        ),
        memory=MemoryInfo(total_mb=ProfileField(value=16384, status=FieldStatus.CAPTURED)),
        locale=LocaleInfo(
            locale=ProfileField(value="en_US.UTF-8", status=FieldStatus.CAPTURED),
            timezone=ProfileField(value="UTC", status=FieldStatus.CAPTURED),
        ),
        network=NetworkInfo(
            latency_ms=ProfileField(value=10.0, status=FieldStatus.REQUESTED),
            packet_loss_percent=ProfileField(value=0.0, status=FieldStatus.REQUESTED),
        ),
    )
    p_file = tmp_path / "base_prof.json"
    p_file.write_text(profile.model_dump_json(), encoding="utf-8")

    res = runner.invoke(
        app,
        [
            "threshold",
            "--profile",
            str(p_file),
            "--command",
            "python3 -c \"print('thresh test')\"",
            "--parameter",
            "network.latency_ms",
            "--low",
            "0",
            "--high",
            "100",
            "--max-trials",
            "4",
        ],
    )
    # The command always passes: there is no boundary in range, and the CLI
    # says so with exit code 3 rather than a green panel.
    assert res.exit_code == 3, res.output
    assert "Threshold Search Result" in res.stdout
    assert "no boundary in range" in res.stdout




def test_cli_connect_local_and_run(tmp_path, monkeypatch):
    import morph.projects

    monkeypatch.setattr(morph.projects, "REGISTRY_DIR", tmp_path / "registry")

    proj_dir = tmp_path / "demo"
    proj_dir.mkdir()
    (proj_dir / "main.py").write_text("print('project ran ok')\n")

    connect = runner.invoke(app, ["connect", str(proj_dir)])
    assert connect.exit_code == 0, connect.output
    assert "Connected: demo" in connect.output

    listed = runner.invoke(app, ["projects"])
    assert "demo" in listed.output

    proj = morph.projects.list_projects(base=tmp_path / "registry")[0]
    run_res = runner.invoke(app, ["run", "--project", proj.id])
    assert run_res.exit_code == 0, run_res.output
    assert "project ran ok" in run_res.output


def test_cli_run_requires_command_or_project():
    result = runner.invoke(app, ["run"])
    assert result.exit_code != 0
    assert "--command or --project" in result.output
