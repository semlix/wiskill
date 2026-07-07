import pytest
from fastapi.testclient import TestClient
from wiskill.web.app import create_app
from wiskill.service import WikiService
from wiskill.store import PageStore
from wiskill.backend import LexicalBackend
from wiskill.auth import UserStore, Role
from wiskill.config import WiskillConfig


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("WISKILL_SECRET", "test-secret")
    store = PageStore(tmp_path / "pages")
    backend = LexicalBackend(tmp_path / "idx")
    service = WikiService(store, backend)
    users = UserStore(tmp_path / "users.json")
    users.add("ed", "pw", Role.EDITOR)
    app = create_app(service, users, WiskillConfig())
    return TestClient(app)


def _login(client, user="ed", pw="pw"):
    return client.post("/login", data={"username": user, "password": pw}, follow_redirects=False)


def test_login_required_redirects(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code in (302, 307)
    assert "/login" in r.headers["location"]


def test_login_create_view_page(client):
    assert _login(client).status_code in (302, 303, 307)
    r = client.post("/notas/x", data={"title": "X", "tags": "a,b", "body": "hola [[y]]"},
                    follow_redirects=False)
    assert r.status_code in (302, 303, 307)
    r = client.get("/notas/x")
    assert r.status_code == 200
    assert "hola" in r.text and "wikilink missing" in r.text


def test_search_route(client):
    _login(client)
    client.post("/foo", data={"title": "Foo", "tags": "", "body": "authentication"},
                follow_redirects=False)
    r = client.get("/search", params={"q": "authentication"})
    assert r.status_code == 200 and "foo" in r.text.lower()


def test_new_page_flow(client):
    _login(client)
    # empty slug re-renders the form (does not 500)
    r = client.post("/new", data={"slug": ""}, follow_redirects=False)
    assert r.status_code == 200
    # a real slug redirects to that page's editor
    r = client.post("/new", data={"slug": "projects/idea"}, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/projects/idea/edit"


def test_bad_credentials(client):
    r = client.post("/login", data={"username": "ed", "password": "nope"})
    assert r.status_code == 200
    assert "inválid" in r.text.lower() or "invalid" in r.text.lower()
