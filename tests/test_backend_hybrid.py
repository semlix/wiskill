from datetime import datetime, timezone

from wiskill.backend import HybridBackend, build_backend, SearchResult
from wiskill.config import WiskillConfig
from wiskill.store import Page


def _page(slug, title, body):
    now = datetime.now(timezone.utc)
    return Page(slug=slug, title=title, tags=[], created=now, updated=now, body=body)


def test_hybrid_finds_by_keyword_and_returns_results(tmp_path, fake_provider):
    b = HybridBackend(tmp_path / "idx", provider=fake_provider, alpha=0.5)
    b.index_page(_page("login", "Login", "authentication errors and passwords"))
    b.index_page(_page("cats", "Cats", "domestic felines behavior"))
    b.commit()
    results = b.search("authentication", limit=5)
    assert results and isinstance(results[0], SearchResult)
    assert any(r.slug == "login" for r in results)


def test_remove_from_hybrid(tmp_path, fake_provider):
    b = HybridBackend(tmp_path / "idx", provider=fake_provider)
    b.index_page(_page("p", "P", "aardvark"))
    b.commit()
    b.remove_page("p")
    b.commit()
    assert b.doc_count() == 0


def test_build_backend_lexical_mode(tmp_path):
    cfg = WiskillConfig(index_dir=tmp_path / "idx", mode="lexical")
    b = build_backend(cfg)
    b.index_page(_page("p", "P", "hello world"))
    b.commit()
    assert b.search("hello")
