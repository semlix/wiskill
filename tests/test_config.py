from pathlib import Path
from wiskill.config import load_config, WiskillConfig


def test_defaults_when_no_file():
    cfg = load_config(None)
    assert isinstance(cfg, WiskillConfig)
    assert cfg.mode == "hybrid"
    assert cfg.lexical_engine == "core"
    assert cfg.alpha == 0.5
    assert cfg.fusion == "rrf"
    assert cfg.provider == "sentence-transformers"
    assert cfg.vector_store == "numpy"
    assert cfg.session_secret_env == "WISKILL_SECRET"
    assert cfg.public_read is False


def test_public_read_parsed(tmp_path):
    cfg_file = tmp_path / "wiskill.toml"
    cfg_file.write_text("[web]\npublic_read = true\n")
    assert load_config(cfg_file).public_read is True


def test_loads_toml_and_resolves_paths(tmp_path):
    cfg_file = tmp_path / "wiskill.toml"
    cfg_file.write_text(
        '[paths]\n'
        'pages = "notes"\n'
        'index = "idx"\n'
        '[search]\n'
        'mode = "lexical"\n'
        'alpha = 0.2\n'
    )
    cfg = load_config(cfg_file)
    assert cfg.mode == "lexical"
    assert cfg.alpha == 0.2
    # relative paths resolve against the config file's directory
    assert cfg.pages_dir == tmp_path / "notes"
    assert cfg.index_dir == tmp_path / "idx"
