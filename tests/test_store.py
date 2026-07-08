import pytest
from wiskill.store import PageStore, Page


@pytest.fixture
def store(tmp_path):
    return PageStore(tmp_path / "pages")


def test_write_then_read_roundtrip(store):
    page = store.write("proyectos/semlix", "El **motor** rápido.", title="Semlix", tags=["a", "b"])
    assert page.slug == "proyectos/semlix"
    got = store.read("proyectos/semlix")
    assert got.title == "Semlix"
    assert got.body == "El **motor** rápido."
    assert got.tags == ["a", "b"]
    assert got.created == page.created
    assert got.updated == page.updated


def test_title_defaults_to_last_slug_segment(store):
    store.write("notas/reunion", "hola")
    assert store.read("notas/reunion").title == "reunion"


def test_missing_page_reads_none(store):
    assert store.read("nope") is None
    assert store.exists("nope") is False


def test_list_and_namespace_filter(store):
    store.write("index", "root")
    store.write("proyectos/a", "x")
    store.write("proyectos/b", "y")
    assert store.list_slugs() == ["index", "proyectos/a", "proyectos/b"]
    assert store.list_slugs("proyectos") == ["proyectos/a", "proyectos/b"]


def test_delete(store):
    store.write("tmp", "x")
    assert store.delete("tmp") is True
    assert store.exists("tmp") is False
    assert store.delete("tmp") is False


@pytest.mark.parametrize("bad", ["../secret", "/etc/passwd", "a/../../b", "a/./b"])
def test_traversal_rejected(store, bad):
    with pytest.raises(ValueError):
        store.slug_to_path(bad)


@pytest.mark.parametrize("bad", ["../secret", "/etc/passwd", "a/../../b", "a/./b", ""])
def test_exists_and_read_degrade_gracefully_on_malformed_slug(store, bad):
    # exists()/read() are predicates called on arbitrary text (e.g. a literal
    # "[[..]]" in a page's prose while resolving wikilinks) — they must never
    # raise, unlike write()/delete() which are real user actions.
    assert store.exists(bad) is False
    assert store.read(bad) is None
