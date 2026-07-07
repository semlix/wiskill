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


@pytest.fixture
def public_client(tmp_path, monkeypatch):
    from wiskill.auth import Principal, Role
    monkeypatch.setenv("WISKILL_SECRET", "s")
    store = PageStore(tmp_path / "pages")
    backend = LexicalBackend(tmp_path / "idx")
    service = WikiService(store, backend)
    service.save("index", "public home body qpub", title="Home", tags=[],
                 principal=Principal("seed", Role.EDITOR))
    users = UserStore(tmp_path / "users.json")
    app = create_app(service, users, WiskillConfig(public_read=True))
    return TestClient(app)


def test_public_read_allows_anonymous_view_and_search(public_client):
    r = public_client.get("/")  # no login
    assert r.status_code == 200 and "public home body qpub" in r.text
    assert public_client.get("/search", params={"q": "public"}).status_code == 200


def test_public_read_still_blocks_anonymous_edit(public_client):
    r = public_client.post("/index", data={"title": "x", "tags": "", "body": "y"},
                           follow_redirects=False)
    assert r.status_code in (302, 303, 307)
    assert "/login" in r.headers["location"]


@pytest.fixture
def private_ns_client(tmp_path, monkeypatch):
    from wiskill.auth import Principal, Role
    monkeypatch.setenv("WISKILL_SECRET", "s")
    store = PageStore(tmp_path / "pages")
    backend = LexicalBackend(tmp_path / "idx")
    service = WikiService(store, backend)
    ed = Principal("ed", Role.EDITOR)
    service.save("index", "public home", title="Home", tags=[], principal=ed)
    service.save("projects/foo", "public project content", title="Foo", tags=[], principal=ed)
    service.save("notes/secret", "my private diary entry xyzzy", title="Secret", tags=[], principal=ed)
    users = UserStore(tmp_path / "users.json")
    users.add("ed", "pw", Role.EDITOR)
    app = create_app(service, users,
                     WiskillConfig(public_read=True, private_namespaces=("notes", "ideas")))
    return TestClient(app)


def test_private_namespace_blocks_anonymous_view(private_ns_client):
    r = private_ns_client.get("/notes/secret", follow_redirects=False)
    assert r.status_code in (302, 303, 307)
    assert "/login" in r.headers["location"]
    # a public page in a non-private namespace stays open to guests
    assert private_ns_client.get("/projects/foo").status_code == 200


def test_private_namespace_excluded_from_anonymous_search(private_ns_client):
    r = private_ns_client.get("/search", params={"q": "diary"})
    assert r.status_code == 200
    assert "notes/secret" not in r.text


def test_private_namespace_hidden_from_anonymous_sidebar(private_ns_client):
    r = private_ns_client.get("/")
    assert "notes/secret" not in r.text
    assert "projects/foo" in r.text


def test_private_namespace_visible_to_logged_in_user(private_ns_client):
    _login(private_ns_client, user="ed", pw="pw")
    r = private_ns_client.get("/notes/secret")
    assert r.status_code == 200 and "private diary entry" in r.text
    assert "notes/secret" in private_ns_client.get("/").text


def test_home_renders_index_page(client):
    _login(client)
    client.post("/index", data={"title": "Home", "tags": "", "body": "welcome body zzz"},
                follow_redirects=False)
    r = client.get("/")
    assert r.status_code == 200
    assert "welcome body zzz" in r.text  # renders the index page, not a listing


def test_new_page_flow(client):
    _login(client)
    # empty slug re-renders the form (does not 500)
    r = client.post("/new", data={"slug": ""}, follow_redirects=False)
    assert r.status_code == 200
    # a real slug redirects to that page's editor
    r = client.post("/new", data={"slug": "projects/idea"}, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/projects/idea/edit"


def test_mcp_require_key_gates_mcp_endpoint(tmp_path, monkeypatch):
    pytest.importorskip("mcp")
    monkeypatch.setenv("WISKILL_SECRET", "s")
    from wiskill.mcp.server import build_mcp
    from wiskill.auth import ApiKeyStore, Principal, Role
    service = WikiService(PageStore(tmp_path / "p"), LexicalBackend(tmp_path / "i"))
    users = UserStore(tmp_path / "u.json")
    keys = ApiKeyStore(tmp_path / "k.json")
    editor_key = keys.create("llm", Role.EDITOR)
    reader_key = keys.create("r", Role.READER)
    mcp = build_mcp(service, Principal("bot", Role.EDITOR), stateless=True, http_path="/")
    app = create_app(service, users, WiskillConfig(mcp_require_key=True),
                     apikeys=keys, mcp_server=mcp)
    # `with` runs the app lifespan so the MCP session manager is initialized.
    with TestClient(app) as c:
        assert c.post("/mcp/", json={}).status_code == 401                                  # no key
        assert c.post("/mcp/", json={}, headers={"X-API-Key": reader_key}).status_code == 401  # reader < editor
        # a valid editor key passes the gate (the MCP app may reject the empty
        # body, but not with 401)
        assert c.post("/mcp/", json={}, headers={"Authorization": f"Bearer {editor_key}"}).status_code != 401


def test_serve_with_mcp_mounts_endpoint(tmp_path):
    pytest.importorskip("mcp")
    from wiskill.mcp.server import build_mcp
    from wiskill.auth import Principal, Role
    store = PageStore(tmp_path / "pages")
    backend = LexicalBackend(tmp_path / "idx")
    service = WikiService(store, backend)
    users = UserStore(tmp_path / "users.json")
    mcp = build_mcp(service, Principal("bot", Role.EDITOR), stateless=True, http_path="/")
    app = create_app(service, users, WiskillConfig(), mcp_server=mcp)
    assert "/mcp" in [getattr(r, "path", None) for r in app.routes]


def test_bad_credentials(client):
    r = client.post("/login", data={"username": "ed", "password": "nope"})
    assert r.status_code == 200
    assert "inválid" in r.text.lower() or "invalid" in r.text.lower()
