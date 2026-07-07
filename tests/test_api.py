import pytest
from fastapi.testclient import TestClient
from wiskill.web.app import create_app
from wiskill.service import WikiService
from wiskill.store import PageStore
from wiskill.backend import LexicalBackend
from wiskill.auth import UserStore, ApiKeyStore, Role
from wiskill.config import WiskillConfig


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    monkeypatch.setenv("WISKILL_SECRET", "s")
    service = WikiService(PageStore(tmp_path / "p"), LexicalBackend(tmp_path / "i"))
    users = UserStore(tmp_path / "u.json")
    keys = ApiKeyStore(tmp_path / "k.json")
    reader_key = keys.create("r", Role.READER)
    editor_key = keys.create("e", Role.EDITOR)
    app = create_app(service, users, WiskillConfig(), apikeys=keys)
    return TestClient(app), reader_key, editor_key


def test_requires_key(ctx):
    client, _, _ = ctx
    assert client.get("/api/pages").status_code == 401


def test_put_get_search_delete(ctx):
    client, reader_key, editor_key = ctx
    eh = {"Authorization": f"Bearer {editor_key}"}
    rh = {"X-API-Key": reader_key}
    r = client.put("/api/pages/notas/x", json={"title": "X", "tags": ["a"], "body": "authentication"}, headers=eh)
    assert r.status_code == 200 and r.json()["slug"] == "notas/x"
    assert client.get("/api/pages/notas/x", headers=rh).json()["title"] == "X"
    assert "notas/x" in client.get("/api/pages", headers=rh).json()["slugs"]
    assert client.get("/api/search", params={"q": "authentication"}, headers=rh).json()["results"]
    assert client.delete("/api/pages/notas/x", headers=rh).status_code == 403
    assert client.delete("/api/pages/notas/x", headers=eh).json()["deleted"] is True


def test_get_missing_404(ctx):
    client, reader_key, _ = ctx
    assert client.get("/api/pages/ghost", headers={"X-API-Key": reader_key}).status_code == 404
