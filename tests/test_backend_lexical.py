from datetime import datetime, timezone

import pytest

from wiskill.backend import LexicalBackend, SearchResult, _approximate_highlight
from wiskill.store import Page


def test_approximate_highlight_wraps_query_terms_and_escapes_html():
    out = _approximate_highlight("<b>login</b> authentication errors", "login authentication")
    assert "&lt;b&gt;" in out and "<script>" not in out
    assert '<b class="match term' in out
    assert out.count('<b class="match term') == 2


def test_approximate_highlight_no_query_terms_just_escapes():
    assert _approximate_highlight("plain <text>", "") == "plain &lt;text&gt;"


def _page(slug, title, body):
    now = datetime.now(timezone.utc)
    return Page(slug=slug, title=title, tags=[], created=now, updated=now, body=body)


def test_bm25_engine(tmp_path):
    pytest.importorskip("bm25s")
    b = LexicalBackend(tmp_path / "idx", engine="bm25")
    b.index_page(_page("login", "Login", "how to fix login authentication errors"))
    b.index_page(_page("cats", "Cats", "domestic felines behavior"))
    b.commit()
    assert b.doc_count() == 2
    results = b.search("authentication")
    # only real matches (bm25s' zero-score non-matches are filtered out)
    assert [r.slug for r in results] == ["login"]
    assert isinstance(results[0], SearchResult)


def test_bm25_engine_snippet_is_approximately_highlighted(tmp_path):
    pytest.importorskip("bm25s")
    b = LexicalBackend(tmp_path / "idx", engine="bm25")
    b.index_page(_page("login", "Login", "how to fix login authentication errors"))
    b.commit()
    snippet = b.search("authentication")[0].snippet
    assert '<b class="match term0">authentication</b>' in snippet


def test_bad_engine_rejected(tmp_path):
    with pytest.raises(ValueError):
        LexicalBackend(tmp_path / "idx", engine="elasticsearch")


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
