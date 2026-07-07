"""SearchBackend: wraps semlix (lexical / semantic / hybrid) over the wiki."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from semlix import index as semlix_index
from semlix.fields import Schema, ID, TEXT, KEYWORD, DATETIME
from semlix.qparser import MultifieldParser

try:
    from semlix.bm25 import BM25Index  # only used when lexical_engine == "bm25"
except ImportError:
    BM25Index = None

from semlix.semantic import HybridSearcher, HybridIndexWriter
from semlix.semantic.stores import NumpyVectorStore

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


def _doc_fields_bm25(page: Page) -> dict:
    """Stored fields for the bm25 engine, which JSON-serializes them: the
    DATETIME must be a compact string, not a datetime object."""
    fields = _doc_fields(page)
    fields["updated"] = page.updated.strftime("%Y%m%d%H%M%S")
    return fields


def _doc_fields(page: Page) -> dict:
    return {
        "slug": page.slug,
        "title": page.title,
        "content": content_for(page),
        "tags": ",".join(page.tags),
        "updated": page.updated,
    }


class LexicalBackend:
    """Pure lexical search over semlix: the core FileIndex (default) or the
    fast bm25s engine. bm25 is bag-of-words (no highlighted snippets), so
    snippets fall back to a plain excerpt."""

    def __init__(self, index_dir: Path, engine: str = "core"):
        if engine not in ("core", "bm25"):
            raise ValueError(f"LexicalBackend engine must be 'core' or 'bm25', got {engine!r}")
        self.engine = engine
        self.index_dir = Path(index_dir)
        self.index_dir.mkdir(parents=True, exist_ok=True)
        if engine == "bm25":
            if BM25Index is None:
                raise RuntimeError("lexical_engine='bm25' needs `pip install bm25s PyStemmer`")
            self.ix = BM25Index(str(self.index_dir), WHOOSH_SCHEMA)
        elif semlix_index.exists_in(str(self.index_dir)):
            self.ix = semlix_index.open_dir(str(self.index_dir))
        else:
            self.ix = semlix_index.create_in(str(self.index_dir), WHOOSH_SCHEMA)
        self._writer = None

    def _w(self):
        if self._writer is None:
            self._writer = self.ix.writer()
        return self._writer

    def index_page(self, page: Page) -> None:
        fields = _doc_fields_bm25(page) if self.engine == "bm25" else _doc_fields(page)
        self._w().update_document(**fields)

    def remove_page(self, slug: str) -> None:
        self._w().delete_by_term("slug", slug)

    def commit(self) -> None:
        if self._writer is not None:
            self._writer.commit()
            self._writer = None

    def doc_count(self) -> int:
        return self.ix.doc_count()

    def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        out: list[SearchResult] = []
        with self.ix.searcher() as s:
            if self.engine == "bm25":
                # bm25s is bag-of-words; it takes the raw query text.
                hits = s.search(query, limit=limit)
            else:
                q = MultifieldParser(["title", "content"], schema=self.ix.schema).parse(query)
                hits = s.search(q, limit=limit)
            for hit in hits:
                # bm25s returns the top-k ranked docs including non-matches
                # (score 0); keep only real matches.
                if self.engine == "bm25" and hit.score <= 0:
                    continue
                # Highlighting needs positions (core only); bm25 → plain excerpt.
                snippet = ""
                if self.engine == "core":
                    snippet = hit.highlights("content")
                if not snippet:
                    snippet = str(hit.get("content", ""))[:200]
                out.append(SearchResult(
                    slug=hit["slug"],
                    title=hit.get("title", hit["slug"]),
                    score=float(hit.score),
                    snippet=snippet,
                ))
        return out


_VECTORS_FILE = "vectors.npz"


class HybridBackend:
    """Lexical (semlix) + semantic (vector store) via semlix HybridSearcher."""

    def __init__(self, index_dir, provider, alpha: float = 0.5,
                 fusion: str = "rrf", lexical_engine: str = "core",
                 mode: str = "hybrid"):
        self.index_dir = Path(index_dir)
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self.provider = provider
        self.alpha = 1.0 if mode == "semantic" else alpha
        self.fusion = fusion

        # Lexical index (core FileIndex or bm25 BM25Index — both are Index).
        lex_dir = self.index_dir / "lexical"
        lex_dir.mkdir(parents=True, exist_ok=True)
        if lexical_engine == "bm25":
            if BM25Index is None:
                raise RuntimeError("lexical_engine='bm25' needs `pip install bm25s PyStemmer`")
            self.ix = BM25Index(str(lex_dir), WHOOSH_SCHEMA)
        else:
            if semlix_index.exists_in(str(lex_dir)):
                self.ix = semlix_index.open_dir(str(lex_dir))
            else:
                self.ix = semlix_index.create_in(str(lex_dir), WHOOSH_SCHEMA)

        # Vector store (persisted to a single .npz next to the lexical index).
        self._vec_path = self.index_dir / _VECTORS_FILE
        if self._vec_path.exists():
            self.vector_store = NumpyVectorStore.load(self._vec_path)
        else:
            self.vector_store = NumpyVectorStore(dimension=provider.dimension)

        self._hwriter = None

    def _hw(self):
        if self._hwriter is None:
            self._hwriter = HybridIndexWriter(
                self.ix, self.vector_store, self.provider,
                embedding_field="content", id_field="slug",
            )
            self._hwriter.__enter__()
        return self._hwriter

    def index_page(self, page: Page) -> None:
        # HybridIndexWriter stores every non-id/content field as vector-store
        # metadata and JSON-serializes it on save(); a raw datetime object
        # (as _doc_fields yields for "updated") is not JSON-serializable, so
        # encode it as the compact numeric string semlix's DATETIME field
        # already accepts for indexing (see DATETIME._parse_datestring).
        fields = _doc_fields(page)
        updated = fields.get("updated")
        if hasattr(updated, "strftime"):
            fields["updated"] = updated.strftime("%Y%m%d%H%M%S")
        self._hw().update_document(**fields)

    def remove_page(self, slug: str) -> None:
        self._hw().delete_by_term("slug", slug)

    def commit(self) -> None:
        if self._hwriter is not None:
            self._hwriter.__exit__(None, None, None)  # commits + embeds pending
            self._hwriter = None
            self.vector_store.save(self._vec_path)

    def doc_count(self) -> int:
        return self.ix.doc_count()

    def search(self, query: str, limit: int = 10) -> list["SearchResult"]:
        searcher = HybridSearcher(
            self.ix, self.vector_store, self.provider,
            default_field="content", id_field="slug",
            alpha=self.alpha, fusion_method=self.fusion,
        )
        hits = searcher.search(query, limit=limit, highlight_fields=["content"])
        out: list[SearchResult] = []
        for h in hits:
            snippet = h.highlights.get("content") or str(h.get("content", ""))[:200]
            out.append(SearchResult(
                slug=h.doc_id,
                title=str(h.get("title", h.doc_id)),
                score=float(h.score),
                snippet=snippet,
            ))
        return out


def build_backend(config):
    """Construct a backend from config. Returns a duck-typed SearchBackend."""
    if config.mode == "lexical":
        return LexicalBackend(config.index_dir, engine=config.lexical_engine)
    provider = _build_provider(config)
    return HybridBackend(
        config.index_dir, provider=provider, alpha=config.alpha,
        fusion=config.fusion, lexical_engine=config.lexical_engine,
        mode=config.mode,
    )


def _build_provider(config):
    if config.provider == "sentence-transformers":
        from semlix.semantic import SentenceTransformerProvider
        return SentenceTransformerProvider(config.model)
    if config.provider == "openai":
        from semlix.semantic import OpenAIProvider
        return OpenAIProvider(model=config.model)
    if config.provider == "cohere":
        from semlix.semantic import CohereProvider
        return CohereProvider(model=config.model)
    raise ValueError(f"unknown provider: {config.provider!r}")


def _manifest_path(backend) -> Path:
    return Path(backend.index_dir) / "manifest.json"


def _load_manifest(backend) -> dict:
    p = _manifest_path(backend)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {}


def _save_manifest(backend, manifest: dict) -> None:
    _manifest_path(backend).write_text(json.dumps(manifest), encoding="utf-8")


def reconcile(backend, store) -> dict:
    """Sync the index to disk: reindex changed pages, drop deleted ones."""
    manifest = _load_manifest(backend)
    on_disk = {}
    indexed = 0
    for page in store.iter_pages():
        digest = hashlib.sha256(content_for(page).encode("utf-8")).hexdigest()
        on_disk[page.slug] = digest
        if manifest.get(page.slug) != digest:
            backend.index_page(page)
            indexed += 1
    removed = 0
    for slug in list(manifest):
        if slug not in on_disk:
            backend.remove_page(slug)
            removed += 1
    if indexed or removed:
        backend.commit()
    _save_manifest(backend, on_disk)
    return {"indexed": indexed, "removed": removed}


def update_manifest_entry(backend, slug: str, page) -> None:
    manifest = _load_manifest(backend)
    if page is None:
        manifest.pop(slug, None)
    else:
        manifest[slug] = hashlib.sha256(content_for(page).encode("utf-8")).hexdigest()
    _save_manifest(backend, manifest)
