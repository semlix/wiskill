from datetime import datetime, timezone

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


def test_write_snapshots_previous_revision(store, tmp_path):
    store.write("a", "v1", title="A", tags=[])
    store.write("a", "v2", title="A", tags=[])
    store.write("a", "v3", title="A", tags=[])
    stamps = store.history("a")
    assert len(stamps) == 2  # v1 and v2 snapshotted; v3 is the current file
    assert stamps == sorted(stamps, reverse=True)  # newest first
    bodies = [store.read_history("a", s).body for s in stamps]
    assert bodies == ["v2", "v1"]
    assert store.read("a").body == "v3"  # current content untouched


def test_first_write_has_no_history(store):
    store.write("a", "v1", title="A", tags=[])
    assert store.history("a") == []


def test_history_empty_for_unknown_slug(store):
    assert store.history("nope") == []
    assert store.read_history("nope", datetime.now(timezone.utc)) is None


def test_history_snapshots_stay_outside_pages_dir(store, tmp_path):
    store.write("a", "v1", title="A", tags=[])
    store.write("a", "v2", title="A", tags=[])
    # A snapshot must never be picked up as if it were its own page.
    assert store.list_slugs() == ["a"]
    assert not store.history_dir.is_relative_to(store.pages_dir)


def test_parse_stamp_roundtrip(store):
    store.write("a", "v1", title="A", tags=[])
    store.write("a", "v2", title="A", tags=[])
    [stamp] = store.history("a")
    text = stamp.strftime("%Y%m%dT%H%M%S%f")
    assert store.parse_stamp(text) == stamp
    assert store.parse_stamp("not-a-stamp") is None
