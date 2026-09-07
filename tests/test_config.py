from morph.config import find_config_path, load_config, save_config
from morph.schema.config import MorphConfig


def test_default_config():
    config = MorphConfig()
    assert config.version == "1.0"
    assert config.default_trials == 5
    assert config.significance_level == 0.05
    assert config.proxy_port == 9876
    assert config.adapters.network == "proxy"


def test_save_and_load_config(tmp_path):
    custom_cfg = MorphConfig(
        version="1.1",
        default_trials=10,
        significance_level=0.01,
        default_command="python custom_app.py",
        proxy_port=8888,
    )
    cfg_file = tmp_path / "morph.yaml"
    save_config(custom_cfg, cfg_file)

    assert cfg_file.exists()

    loaded = load_config(cfg_file)
    assert loaded.version == "1.1"
    assert loaded.default_trials == 10
    assert loaded.significance_level == 0.01
    assert loaded.default_command == "python custom_app.py"
    assert loaded.proxy_port == 8888


def test_find_config_path(tmp_path):
    nested_dir = tmp_path / "src" / "pkg"
    nested_dir.mkdir(parents=True)

    cfg_file = tmp_path / "morph.yaml"
    save_config(MorphConfig(default_trials=7), cfg_file)

    found = find_config_path(nested_dir)
    assert found is not None
    assert found == cfg_file

    loaded = load_config(nested_dir)
    assert loaded.default_trials == 7


def test_github_section_defaults_and_roundtrip(tmp_path):
    from morph.config import load_config, save_config
    from morph.schema.config import MorphConfig

    cfg = MorphConfig()
    assert cfg.github.client_id is None
    assert cfg.github.scope == "repo,read:user"
    cfg.github.client_id = "Iv1.abc123"
    path = tmp_path / "morph.yaml"
    save_config(cfg, path)
    assert load_config(path).github.client_id == "Iv1.abc123"
