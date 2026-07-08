"""PageStore: Markdown files on disk are the source of truth."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

import yaml

from wiskill._atomic import atomic_write_text

_SLUG_SEGMENT = re.compile(r"^[A-Za-z0-9._-]+$")
_FRONT_MATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)


@dataclass
class Page:
    slug: str
    title: str
    tags: list[str]
    created: datetime
    updated: datetime
    body: str = ""


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


class PageStore:
    def __init__(self, pages_dir: Path):
        self.pages_dir = Path(pages_dir)
        self.pages_dir.mkdir(parents=True, exist_ok=True)

    def slug_to_path(self, slug: str) -> Path:
        slug = slug.strip()
        if slug.startswith("/"):
            raise ValueError("absolute slug not allowed")
        slug = slug.strip("/")
        if not slug:
            raise ValueError("empty slug")
        segments = slug.split("/")
        for seg in segments:
            if not _SLUG_SEGMENT.match(seg) or seg in (".", ".."):
                raise ValueError(f"invalid slug segment: {seg!r}")
        path = (self.pages_dir / Path(*segments)).with_suffix(".md")
        # Defense in depth: ensure the resolved path stays inside pages_dir.
        root = self.pages_dir.resolve()
        if not str(path.resolve()).startswith(str(root)):
            raise ValueError("slug escapes pages directory")
        return path

    def path_to_slug(self, path: Path) -> str:
        rel = Path(path).resolve().relative_to(self.pages_dir.resolve())
        return rel.with_suffix("").as_posix()

    def exists(self, slug: str) -> bool:
        # A malformed slug (e.g. a literal "[[..]]" in prose/code resolving
        # to a ".." segment) can't exist as a page — that's not the same as
        # an error the caller should have to handle. render_html calls this
        # per-wikilink while rendering arbitrary user content, so it must
        # never raise.
        try:
            path = self.slug_to_path(slug)
        except ValueError:
            return False
        return path.exists()

    def read(self, slug: str) -> Page | None:
        try:
            path = self.slug_to_path(slug)
        except ValueError:
            return None
        if not path.exists():
            return None
        raw = path.read_text(encoding="utf-8")
        meta, body = self._split_front_matter(raw)
        default_title = slug.rsplit("/", 1)[-1]
        return Page(
            slug=slug,
            title=str(meta.get("title") or default_title),
            tags=list(meta.get("tags") or []),
            created=self._parse_dt(meta.get("created")),
            updated=self._parse_dt(meta.get("updated")),
            body=body,
        )

    def write(self, slug: str, body: str, title: str | None = None,
              tags: list[str] | None = None) -> Page:
        path = self.slug_to_path(slug)
        path.parent.mkdir(parents=True, exist_ok=True)
        now = _now()
        existing = self.read(slug)
        created = existing.created if existing else now
        page = Page(
            slug=slug,
            title=title or (existing.title if existing else slug.rsplit("/", 1)[-1]),
            tags=tags if tags is not None else (existing.tags if existing else []),
            created=created,
            updated=now,
            body=body,
        )
        front = {
            "title": page.title,
            "tags": page.tags,
            "created": page.created.isoformat(),
            "updated": page.updated.isoformat(),
        }
        text = "---\n" + yaml.safe_dump(front, allow_unicode=True, sort_keys=False) + "---\n" + body
        atomic_write_text(path, text)
        return page

    def delete(self, slug: str) -> bool:
        path = self.slug_to_path(slug)
        if not path.exists():
            return False
        path.unlink()
        return True

    def list_slugs(self, namespace: str | None = None) -> list[str]:
        slugs = [self.path_to_slug(p) for p in self.pages_dir.rglob("*.md")]
        if namespace:
            prefix = namespace.strip("/") + "/"
            slugs = [s for s in slugs if s.startswith(prefix)]
        return sorted(slugs)

    def iter_pages(self) -> Iterator[Page]:
        for slug in self.list_slugs():
            page = self.read(slug)
            if page is not None:
                yield page

    @staticmethod
    def _split_front_matter(raw: str) -> tuple[dict, str]:
        m = _FRONT_MATTER.match(raw)
        if not m:
            return {}, raw
        try:
            meta = yaml.safe_load(m.group(1)) or {}
            if not isinstance(meta, dict):
                meta = {}
        except yaml.YAMLError:
            meta = {}
        return meta, m.group(2)

    @staticmethod
    def _parse_dt(value) -> datetime:
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                pass
        return _now()
