import pytest
from fastapi.testclient import TestClient
from wiskill.web.app import create_app, build_nav_tree, _tag_cloud
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


def test_search_pagination_default_page_size_and_next_link(client):
    _login(client)
    for i in range(12):
        client.post(f"/pagetest/{i}", data={"title": f"Page {i}", "tags": "",
                    "body": "paginationterm"}, follow_redirects=False)
    r = client.get("/search", params={"q": "paginationterm"})
    assert r.status_code == 200
    assert r.text.count('class="result-title"') == 10
    assert "Next" in r.text and "Prev" not in r.text

    r2 = client.get("/search", params={"q": "paginationterm", "page": 2})
    assert r2.status_code == 200
    assert r2.text.count('class="result-title"') == 2
    assert "Prev" in r2.text and "Next" not in r2.text


def test_search_page_size_selector(client):
    _login(client)
    for i in range(12):
        client.post(f"/pagetest/{i}", data={"title": f"Page {i}", "tags": "",
                    "body": "paginationterm"}, follow_redirects=False)
    r = client.get("/search", params={"q": "paginationterm", "n": 25})
    assert r.status_code == 200
    assert r.text.count('class="result-title"') == 12
    assert "Next" not in r.text
    assert '<option value="25" selected>' in r.text


def test_search_invalid_page_size_falls_back_to_default(client):
    _login(client)
    client.post("/foo", data={"title": "Foo", "tags": "", "body": "authentication"},
                follow_redirects=False)
    r = client.get("/search", params={"q": "authentication", "n": 999})
    assert r.status_code == 200
    assert '<option value="10" selected>' in r.text


def test_search_result_snippet_has_no_raw_markdown_or_score(client):
    _login(client)
    client.post("/projects/foo", data={
        "title": "Foo", "tags": "",
        "body": "# Foo\nWelcome to my **semantic notebook**, see [[bar|Bar]] for authtoken details."},
        follow_redirects=False)
    r = client.get("/search", params={"q": "authtoken"})
    assert r.status_code == 200
    assert "**" not in r.text and "[[" not in r.text
    # breadcrumb-style path built from the slug
    assert "projects › foo" in r.text
    # no raw relevance score digits shown
    import re
    assert not re.search(r"0\.\d{3}", r.text)


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


def test_tag_chip_links_to_tag_page_and_lists_it(client):
    _login(client)
    client.post("/notas/x", data={"title": "X", "tags": "auth, notes", "body": "hola"},
                follow_redirects=False)
    client.post("/notas/y", data={"title": "Y", "tags": "notes", "body": "adios"},
                follow_redirects=False)
    r = client.get("/notas/x")
    assert r.status_code == 200
    assert '<a href="/tags/auth">#auth</a>' in r.text

    r = client.get("/tags")
    assert r.status_code == 200
    assert '<a class="tag-cloud-item tier-5" href="/tags/notes" title="2 pages">#notes</a>' in r.text
    assert '<a class="tag-cloud-item tier-1" href="/tags/auth" title="1 page">#auth</a>' in r.text

    r = client.get("/tags/notes")
    assert r.status_code == 200
    assert "notas/x" in r.text and "notas/y" in r.text

    r = client.get("/tags/auth")
    assert r.status_code == 200
    assert 'result-title" href="/notas/x"' in r.text
    assert 'result-title" href="/notas/y"' not in r.text


def test_tags_index_and_tag_page_exclude_private_namespace_for_anon(tmp_path, monkeypatch):
    from wiskill.auth import Principal, Role
    monkeypatch.setenv("WISKILL_SECRET", "s")
    service = WikiService(PageStore(tmp_path / "pages"), LexicalBackend(tmp_path / "idx"))
    ed = Principal("ed", Role.EDITOR)
    service.save("projects/foo", "public", title="Foo", tags=["shared"], principal=ed)
    service.save("notes/secret", "private diary", title="Secret", tags=["shared", "diary"],
                 principal=ed)
    users = UserStore(tmp_path / "users.json")
    app = create_app(service, users,
                     WiskillConfig(public_read=True, private_namespaces=("notes",)))
    c = TestClient(app)

    r = c.get("/tags")
    assert r.status_code == 200
    assert 'title="1 page"' in r.text  # "shared" only counts the public page
    assert "diary" not in r.text  # only appears on the private page

    r = c.get("/tags/shared")
    assert r.status_code == 200
    assert "projects/foo" in r.text and "notes/secret" not in r.text


def test_page_shows_toc_and_backlinks(client):
    _login(client)
    client.post("/target", data={"title": "Target", "tags": "",
                "body": "## Section One\nbody\n\n## Section Two\nbody"},
                follow_redirects=False)
    client.post("/linker", data={"title": "Linker", "tags": "", "body": "see [[target]]"},
                follow_redirects=False)

    r = client.get("/target")
    assert r.status_code == 200
    assert '<li class="toc-h2"><a href="#section-one">Section One</a></li>' in r.text
    assert '<a href="/linker" title="linker">Linker</a>' in r.text  # backlinks panel


def test_backlinks_exclude_private_namespace_linker_for_anon(tmp_path, monkeypatch):
    from wiskill.auth import Principal, Role
    monkeypatch.setenv("WISKILL_SECRET", "s")
    service = WikiService(PageStore(tmp_path / "pages"), LexicalBackend(tmp_path / "idx"))
    ed = Principal("ed", Role.EDITOR)
    service.save("target", "public target", title="Target", tags=[], principal=ed)
    service.save("notes/secret", "see [[target]]", title="Secret", tags=[], principal=ed)
    users = UserStore(tmp_path / "users.json")
    app = create_app(service, users,
                     WiskillConfig(public_read=True, private_namespaces=("notes",)))
    r = TestClient(app).get("/target")
    assert r.status_code == 200
    assert "Linked from" not in r.text  # the only backlink is from a private page


def test_home_renders_index_page(client):
    _login(client)
    client.post("/index", data={"title": "Home", "tags": "", "body": "welcome body zzz"},
                follow_redirects=False)
    r = client.get("/")
    assert r.status_code == 200
    assert "welcome body zzz" in r.text  # renders the index page, not a listing


def test_history_list_view_and_restore_flow(client):
    _login(client)
    client.post("/a", data={"title": "A", "tags": "", "body": "v1"}, follow_redirects=False)
    client.post("/a", data={"title": "A", "tags": "", "body": "v2"}, follow_redirects=False)

    r = client.get("/a/history")
    assert r.status_code == 200
    assert r.text.count('class="result-title"') == 1  # v1 snapshotted, v2 is current

    href = r.text.split('href="/a/history/')[1].split('"')[0]
    r = client.get(f"/a/history/{href}")
    assert r.status_code == 200
    assert "v1" in r.text
    assert "Restore this revision" in r.text

    r = client.post(f"/a/history/{href}/restore", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/a"
    assert client.get("/a").text.count("v1") >= 1
    # restoring v1 (over v2) snapshotted v2, so history now has 2 entries
    assert client.get("/a/history").text.count('class="result-title"') == 2


def test_history_requires_login(client):
    client.post("/a", data={"title": "A", "tags": "", "body": "v1"}, follow_redirects=False)  # anon can't; ignore
    r = client.get("/a/history", follow_redirects=False)
    assert r.status_code == 307 and "/login" in r.headers["location"]


def test_history_unknown_revision_404s(client):
    _login(client)
    client.post("/a", data={"title": "A", "tags": "", "body": "v1"}, follow_redirects=False)
    assert client.get("/a/history/20260101T000000000000").status_code == 404
    assert client.post("/a/history/20260101T000000000000/restore").status_code == 404


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


def test_stylesheet_link_is_cache_busted(client):
    r = client.get("/login")
    assert r.status_code == 200
    assert "/static/style.css?v=" in r.text


def test_footer_shows_version_without_repeating_brand_name(client):
    _login(client)
    r = client.get("/")
    assert r.status_code == 200
    import re
    assert re.search(r"wiskill v\d+\.\d+\.\d+", r.text)
    assert "wiskill on GitHub" not in r.text
    assert "built with wiskill" not in r.text


def test_build_nav_tree_groups_namespaces_before_leaves():
    tree = build_nav_tree([
        "index",
        "projects",
        "projects/bashblog",
        "projects/bpaste",
        "projects/semlix",
        "projects/semlix/engines",
        "projects/wiskill",
        "projects/wiskill/cli",
    ])
    names = list(tree["projects"]["children"].keys())
    # namespaces with sub-pages (semlix, wiskill) group before leaf pages
    # (bashblog, bpaste); alphabetical within each group.
    assert names == ["semlix", "wiskill", "bashblog", "bpaste"]


def test_tag_cloud_scales_tier_by_relative_weight():
    cloud = _tag_cloud({"rare": 1, "mid": 3, "common": 5})
    by_tag = {tag: tier for tag, _count, tier in cloud}
    assert by_tag == {"rare": 1, "mid": 3, "common": 5}
    assert [tag for tag, _count, _tier in cloud] == ["common", "mid", "rare"]  # alphabetical


def test_tag_cloud_flat_weight_when_all_counts_equal():
    cloud = _tag_cloud({"a": 2, "b": 2})
    assert [tier for _tag, _count, tier in cloud] == [3, 3]


def test_tag_cloud_empty():
    assert _tag_cloud({}) == []


@pytest.fixture
def sitemap_client(tmp_path, monkeypatch):
    from wiskill.auth import Principal, Role
    monkeypatch.setenv("WISKILL_SECRET", "s")
    store = PageStore(tmp_path / "pages")
    backend = LexicalBackend(tmp_path / "idx")
    service = WikiService(store, backend)
    ed = Principal("ed", Role.EDITOR)
    service.save("index", "home body", title="Home", tags=[], principal=ed)
    service.save("projects/foo", "foo body", title="Foo", tags=[], principal=ed)
    service.save("notes/secret", "secret body", title="Secret", tags=[], principal=ed)
    users = UserStore(tmp_path / "users.json")
    app = create_app(service, users, WiskillConfig(
        public_read=True, site_url="https://example.com",
        private_namespaces=("notes",)))
    return TestClient(app)


def test_sitemap_lists_public_pages_excludes_private(sitemap_client):
    r = sitemap_client.get("/sitemap.xml")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/xml")
    assert "<loc>https://example.com/projects/foo</loc>" in r.text
    assert "<loc>https://example.com/index</loc>" in r.text
    assert "notes/secret" not in r.text


def test_sitemap_404_without_site_url(public_client):
    # public_client (existing fixture): public_read=True, site_url unset
    assert public_client.get("/sitemap.xml").status_code == 404


def test_sitemap_404_when_public_read_false_even_with_site_url(tmp_path, monkeypatch):
    monkeypatch.setenv("WISKILL_SECRET", "s")
    service = WikiService(PageStore(tmp_path / "p"), LexicalBackend(tmp_path / "i"))
    users = UserStore(tmp_path / "u.json")
    app = create_app(service, users, WiskillConfig(site_url="https://example.com"))
    assert TestClient(app).get("/sitemap.xml").status_code == 404


def test_robots_always_200_blocks_all_except_googlebot(client):
    r = client.get("/robots.txt")
    assert r.status_code == 200
    assert "Disallow: /" in r.text
    assert "User-agent: Googlebot" in r.text
    assert "Allow: /" in r.text
    assert "Sitemap:" not in r.text  # no site_url configured on `client`


def test_robots_includes_sitemap_line_when_configured(sitemap_client):
    r = sitemap_client.get("/robots.txt")
    assert r.status_code == 200
    assert "Sitemap: https://example.com/sitemap.xml" in r.text
