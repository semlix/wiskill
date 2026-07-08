"""PageStore: Markdown files on disk are the source of truth."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
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


_HISTORY_STAMP = "%Y%m%dT%H%M%S%f"


class PageStore:
    def __init__(self, pages_dir: Path, history_dir: Path | None = None):
        self.pages_dir = Path(pages_dir)
        self.pages_dir.mkdir(parents=True, exist_ok=True)
        # Snapshots of prior revisions, one file per save. Defaults to a
        # sibling of pages_dir (never nested inside it — list_slugs()/
        # iter_pages() rglob pages_dir for "*.md" and would otherwise treat
        # every snapshot as its own page).
        self.history_dir = Path(history_dir) if history_dir else self.pages_dir.parent / "history"

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

    def _history_dir_for(self, slug: str) -> Path:
        return self.history_dir.joinpath(*slug.split("/"))

    @staticmethod
    def parse_stamp(stamp: str) -> datetime | None:
        """Parse a history() timestamp back from its URL path-segment form
        (e.g. from `/{slug}/history/{stamp}`); None if malformed."""
        try:
            return datetime.strptime(stamp, _HISTORY_STAMP).replace(tzinfo=timezone.utc)
        except ValueError:
            return None

    @staticmethod
    def format_stamp(stamp: datetime) -> str:
        """Inverse of parse_stamp — the URL path-segment form of a
        history() timestamp."""
        return stamp.strftime(_HISTORY_STAMP)

    def _snapshot(self, slug: str, raw_text: str) -> None:
        """Save the file content being replaced, named by the current instant
        (microsecond precision, nudged forward on collision — two saves in
        the same request-response cycle are the only realistic case)."""
        hist_dir = self._history_dir_for(slug)
        hist_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc)
        path = hist_dir / f"{stamp.strftime(_HISTORY_STAMP)}.md"
        while path.exists():
            stamp += timedelta(microseconds=1)
            path = hist_dir / f"{stamp.strftime(_HISTORY_STAMP)}.md"
        atomic_write_text(path, raw_text)

    def history(self, slug: str) -> list[datetime]:
        """Timestamps of prior revisions of `slug`, newest first. The
        current content (in the main page file) isn't included."""
        hist_dir = self._history_dir_for(slug)
        if not hist_dir.exists():
            return []
        stamps = []
        for f in hist_dir.glob("*.md"):
            try:
                stamps.append(datetime.strptime(f.stem, _HISTORY_STAMP).replace(tzinfo=timezone.utc))
            except ValueError:
                continue
        return sorted(stamps, reverse=True)

    def read_history(self, slug: str, stamp: datetime) -> Page | None:
        """A prior revision of `slug` as it was at `stamp` (from history())."""
        path = self._history_dir_for(slug) / f"{stamp.strftime(_HISTORY_STAMP)}.md"
        if not path.exists():
            return None
        meta, body = self._split_front_matter(path.read_text(encoding="utf-8"))
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
        if existing is not None:
            self._snapshot(slug, path.read_text(encoding="utf-8"))
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
