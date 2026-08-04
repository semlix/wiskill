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


def test_list_pages_namespace_and_tag_filters(ctx):
    client, reader_key, editor_key = ctx
    eh = {"Authorization": f"Bearer {editor_key}"}
    rh = {"X-API-Key": reader_key}
    client.put("/api/pages/skills/foo", json={"tags": ["skill"], "body": "x"}, headers=eh)
    client.put("/api/pages/skills/bar", json={"tags": ["skill", "draft"], "body": "y"}, headers=eh)
    client.put("/api/pages/notes/baz", json={"tags": ["draft"], "body": "z"}, headers=eh)

    assert sorted(client.get("/api/pages", headers=rh).json()["slugs"]) == [
        "notes/baz", "skills/bar", "skills/foo"]  # no params: unchanged, every slug

    r = client.get("/api/pages", params={"namespace": "skills"}, headers=rh)
    assert sorted(r.json()["slugs"]) == ["skills/bar", "skills/foo"]

    r = client.get("/api/pages", params={"tag": "skill"}, headers=rh)
    assert sorted(r.json()["slugs"]) == ["skills/bar", "skills/foo"]

    r = client.get("/api/pages", params={"namespace": "skills", "tag": "draft"}, headers=rh)
    assert r.json()["slugs"] == ["skills/bar"]  # AND, not OR

    r = client.get("/api/pages", params={"namespace": "nope", "tag": "nope"}, headers=rh)
    assert r.json()["slugs"] == []
