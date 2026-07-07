from datetime import datetime, timezone

from wiskill.backend import LexicalBackend, SearchResult
from wiskill.store import Page


def _page(slug, title, body):
    now = datetime.now(timezone.utc)
    return Page(slug=slug, title=title, tags=[], created=now, updated=now, body=body)


def test_index_and_search(tmp_path):
    b = LexicalBackend(tmp_path / "idx")
    b.index_page(_page("login", "Login", "how to fix login authentication errors"))
    b.index_page(_page("cats", "Cats", "domestic felines and their behavior"))
    b.commit()
    results = b.search("authentication")
    assert len(results) == 1
    assert isinstance(results[0], SearchResult)
    assert results[0].slug == "login"
    assert results[0].snippet  # non-empty highlight


def test_update_replaces_same_slug(tmp_path):
    b = LexicalBackend(tmp_path / "idx")
    b.index_page(_page("p", "P", "aardvark"))
    b.commit()
    b.index_page(_page("p", "P", "zebra"))
    b.commit()
    assert b.doc_count() == 1
    assert b.search("zebra") and not b.search("aardvark")


def test_remove(tmp_path):
    b = LexicalBackend(tmp_path / "idx")
    b.index_page(_page("p", "P", "aardvark"))
    b.commit()
    b.remove_page("p")
    b.commit()
    assert b.doc_count() == 0
