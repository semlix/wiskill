import pytest
from wiskill.mcp.server import WikiTools
from wiskill.service import WikiService, PermissionError
from wiskill.store import PageStore
from wiskill.backend import LexicalBackend
from wiskill.auth import Principal, Role


@pytest.fixture
def tools(tmp_path):
    service = WikiService(PageStore(tmp_path / "p"), LexicalBackend(tmp_path / "i"))
    return WikiTools(service, Principal("bot", Role.EDITOR))


def test_write_read_search_list_delete(tools):
    out = tools.wiki_write("notas/x", "authentication notes", title="X", tags=["a"])
    assert out["slug"] == "notas/x"
    assert tools.wiki_read("notas/x")["title"] == "X"
    assert any(r["slug"] == "notas/x" for r in tools.wiki_search("authentication"))
    assert tools.wiki_list() == ["notas/x"]
    assert tools.wiki_delete("notas/x") is True
    assert tools.wiki_read("notas/x") is None


def test_transport_map_and_validation():
    from wiskill.mcp.server import _TRANSPORTS, run_server
    assert _TRANSPORTS == {"stdio": "stdio", "http": "streamable-http", "sse": "sse"}
    with pytest.raises(ValueError):
        run_server(transport="tcp")  # not a valid transport


def test_reader_cannot_write(tmp_path):
    service = WikiService(PageStore(tmp_path / "p"), LexicalBackend(tmp_path / "i"))
    reader_tools = WikiTools(service, Principal("r", Role.READER))
    with pytest.raises(PermissionError):
        reader_tools.wiki_write("x", "body")
