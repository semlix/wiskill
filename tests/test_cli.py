import json
from wiskill.cli import main
from wiskill.auth import UserStore, ApiKeyStore, Role


def _cfg(tmp_path):
    cfg = tmp_path / "wiskill.toml"
    cfg.write_text(
        f'[paths]\npages = "{tmp_path/"pages"}"\nindex = "{tmp_path/"idx"}"\n'
        f'[search]\nmode = "lexical"\n'
        f'[auth]\nusers_file = "{tmp_path/"u.json"}"\napikeys_file = "{tmp_path/"k.json"}"\n'
    )
    return str(cfg)


def test_init_and_reindex(tmp_path, capsys):
    cfg = _cfg(tmp_path)
    assert main(["--config", cfg, "init"]) == 0
    assert (tmp_path / "pages" / "index.md").exists()
    assert main(["--config", cfg, "reindex"]) == 0
    assert "indexed" in capsys.readouterr().out


def test_reindex_rebuild(tmp_path, capsys):
    cfg = _cfg(tmp_path)
    assert main(["--config", cfg, "init"]) == 0
    capsys.readouterr()
    # --rebuild wipes the index and reindexes every page from disk.
    assert main(["--config", cfg, "reindex", "--rebuild"]) == 0
    out = capsys.readouterr().out
    assert "indexed=1" in out  # the seed index page rebuilt from scratch


def test_user_add_and_list(tmp_path, capsys):
    cfg = _cfg(tmp_path)
    assert main(["--config", cfg, "user", "add", "alice", "--role", "admin", "--password", "pw"]) == 0
    assert UserStore(tmp_path / "u.json").authenticate("alice", "pw").role == Role.ADMIN
    main(["--config", cfg, "user", "list"])
    assert "alice" in capsys.readouterr().out


def test_apikey_add_prints_key(tmp_path, capsys):
    cfg = _cfg(tmp_path)
    assert main(["--config", cfg, "apikey", "add", "bot", "--role", "editor"]) == 0
    printed = capsys.readouterr().out
    assert len(printed.strip().splitlines()[-1]) > 20
    assert ApiKeyStore(tmp_path / "k.json").list_keys() == [("bot", Role.EDITOR)]
