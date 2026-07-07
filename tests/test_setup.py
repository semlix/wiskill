import os
from wiskill._setup import load_env_file


def test_load_env_from_config_dir(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text(
        "# a comment\n"
        "WISKILL_SECRET=abc123\n"
        'WISKILL_API_KEY="quoted-key"\n'
        "\n"
    )
    cfg = tmp_path / "wiskill.toml"
    cfg.write_text("[paths]\n")
    monkeypatch.delenv("WISKILL_SECRET", raising=False)
    monkeypatch.delenv("WISKILL_API_KEY", raising=False)

    loaded = load_env_file(str(cfg))
    assert str(tmp_path / ".env") in loaded
    assert os.environ["WISKILL_SECRET"] == "abc123"
    assert os.environ["WISKILL_API_KEY"] == "quoted-key"


def test_real_env_wins_over_file(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("WISKILL_SECRET=from-file\n")
    cfg = tmp_path / "wiskill.toml"
    cfg.write_text("[paths]\n")
    monkeypatch.setenv("WISKILL_SECRET", "from-env")

    load_env_file(str(cfg))
    assert os.environ["WISKILL_SECRET"] == "from-env"  # setdefault → env wins
