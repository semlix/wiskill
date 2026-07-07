import pytest
from wiskill.service import WikiService, PermissionError
from wiskill.store import PageStore
from wiskill.backend import LexicalBackend
from wiskill.auth import Principal, Role


@pytest.fixture
def svc(tmp_path):
    store = PageStore(tmp_path / "pages")
    backend = LexicalBackend(tmp_path / "idx")
    return WikiService(store, backend)


EDITOR = Principal("e", Role.EDITOR)
READER = Principal("r", Role.READER)


def test_save_then_get_and_search(svc):
    svc.save("login", "authentication help", title="Login", tags=["auth"], principal=EDITOR)
    assert svc.get("login").title == "Login"
    assert svc.search("authentication")[0].slug == "login"


def test_render_resolves_wikilinks(svc):
    svc.save("a", "link to [[b]]", title="A", tags=[], principal=EDITOR)
    html = svc.render("a")
    assert "wikilink missing" in html  # b doesn't exist yet


def test_reader_cannot_write(svc):
    with pytest.raises(PermissionError):
        svc.save("x", "body", title="X", tags=[], principal=READER)


def test_remove_requires_editor(svc):
    svc.save("x", "body", title="X", tags=[], principal=EDITOR)
    with pytest.raises(PermissionError):
        svc.remove("x", principal=READER)
    assert svc.remove("x", principal=EDITOR) is True
    assert not svc.search("body")
