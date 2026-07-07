from wiskill.auth import ApiKeyStore, Role


def test_create_and_verify(tmp_path):
    ks = ApiKeyStore(tmp_path / "keys.json")
    key = ks.create("ci-bot", Role.EDITOR)
    assert isinstance(key, str) and len(key) > 20
    p = ks.verify(key)
    assert p is not None and p.role == Role.EDITOR and p.username == "ci-bot"
    assert ks.verify("not-a-key") is None


def test_plaintext_not_stored(tmp_path):
    path = tmp_path / "keys.json"
    key = ApiKeyStore(path).create("x", Role.READER)
    assert key not in path.read_text()


def test_remove(tmp_path):
    ks = ApiKeyStore(tmp_path / "keys.json")
    ks.create("z", Role.READER)
    assert ks.remove("z") is True
    assert ks.list_keys() == []
