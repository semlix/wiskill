"""SearchBackend: wraps semlix (lexical / semantic / hybrid) over the wiki."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from semlix import index as semlix_index
from semlix.fields import Schema, ID, TEXT, KEYWORD, DATETIME
from semlix.qparser import MultifieldParser

from wiskill.store import Page

WHOOSH_SCHEMA = Schema(
    slug=ID(stored=True, unique=True),
    title=TEXT(stored=True),
    content=TEXT(stored=True),
    tags=KEYWORD(stored=True, commas=True),
    updated=DATETIME(stored=True),
)


@dataclass
class SearchResult:
    slug: str
    title: str
    score: float
    snippet: str


def content_for(page: Page) -> str:
    return f"{page.title}\n{page.body}"


def _doc_fields(page: Page) -> dict:
    return {
        "slug": page.slug,
        "title": page.title,
        "content": content_for(page),
        "tags": ",".join(page.tags),
        "updated": page.updated,
    }


class LexicalBackend:
    """Pure lexical search over a semlix core FileIndex."""

    def __init__(self, index_dir: Path, engine: str = "core"):
        if engine != "core":
            raise ValueError(f"LexicalBackend supports engine='core', got {engine!r}")
        self.index_dir = Path(index_dir)
        self.index_dir.mkdir(parents=True, exist_ok=True)
        if semlix_index.exists_in(str(self.index_dir)):
            self.ix = semlix_index.open_dir(str(self.index_dir))
        else:
            self.ix = semlix_index.create_in(str(self.index_dir), WHOOSH_SCHEMA)
        self._writer = None

    def _w(self):
        if self._writer is None:
            self._writer = self.ix.writer()
        return self._writer

    def index_page(self, page: Page) -> None:
        self._w().update_document(**_doc_fields(page))

    def remove_page(self, slug: str) -> None:
        self._w().delete_by_term("slug", slug)

    def commit(self) -> None:
        if self._writer is not None:
            self._writer.commit()
            self._writer = None

    def doc_count(self) -> int:
        return self.ix.doc_count()

    def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        parser = MultifieldParser(["title", "content"], schema=self.ix.schema)
        q = parser.parse(query)
        out: list[SearchResult] = []
        with self.ix.searcher() as s:
            hits = s.search(q, limit=limit)
            for hit in hits:
                snippet = hit.highlights("content") or (hit.get("content", "")[:200])
                out.append(SearchResult(
                    slug=hit["slug"],
                    title=hit.get("title", hit["slug"]),
                    score=float(hit.score),
                    snippet=snippet,
                ))
        return out
