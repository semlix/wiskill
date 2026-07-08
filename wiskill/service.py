"""WikiService: the single interface every adapter (web/MCP/CLI) uses."""
from __future__ import annotations

from wiskill.auth import Principal, Role
from wiskill.backend import reconcile, update_manifest_entry
from wiskill.markup import render_html
from wiskill.store import Page, PageStore


class PermissionError(Exception):
    """Raised when a principal's role is insufficient for an operation."""


class WikiService:
    def __init__(self, store: PageStore, backend):
        self.store = store
        self.backend = backend

    def _require(self, principal: Principal, needed: Role) -> None:
        if principal is None or not principal.role.allows(needed):
            raise PermissionError(f"requires role {needed.value}")

    def get(self, slug: str) -> Page | None:
        return self.store.read(slug)

    def _direct_children(self, slug: str) -> list[tuple[str, str, str]]:
        """Direct sub-pages of `slug` (not deeper descendants), newest first,
        as (slug, title, updated_display) for the {{children}} markup tag."""
        depth = len(slug.split("/")) + 1
        direct_slugs = [s for s in self.store.list_slugs(slug)
                        if len(s.split("/")) == depth]
        pages = [p for p in (self.store.read(s) for s in direct_slugs) if p is not None]
        pages.sort(key=lambda p: p.updated, reverse=True)
        return [(p.slug, p.title, p.updated.strftime("%b %d, %Y")) for p in pages]

    def render(self, slug: str) -> str | None:
        page = self.store.read(slug)
        if page is None:
            return None
        children = self._direct_children(slug)
        return render_html(page.body, self.store.exists, children=children)

    def save(self, slug: str, body: str, title, tags, principal: Principal) -> Page:
        self._require(principal, Role.EDITOR)
        page = self.store.write(slug, body, title=title, tags=tags)
        self.backend.index_page(page)
        self.backend.commit()
        update_manifest_entry(self.backend, slug, page)
        return page

    def remove(self, slug: str, principal: Principal) -> bool:
        self._require(principal, Role.EDITOR)
        removed = self.store.delete(slug)
        if removed:
            self.backend.remove_page(slug)
            self.backend.commit()
            update_manifest_entry(self.backend, slug, None)
        return removed

    def search(self, query: str, limit: int = 10):
        return self.backend.search(query, limit=limit)

    def list_pages(self, namespace: str | None = None) -> list[str]:
        return self.store.list_slugs(namespace)

    def tags_index(self) -> dict[str, int]:
        """{tag: page count}, for browsing all tags in use."""
        counts: dict[str, int] = {}
        for page in self.store.iter_pages():
            for tag in page.tags:
                counts[tag] = counts.get(tag, 0) + 1
        return counts

    def pages_by_tag(self, tag: str) -> list[Page]:
        """Pages carrying `tag`, newest-updated first."""
        pages = [p for p in self.store.iter_pages() if tag in p.tags]
        pages.sort(key=lambda p: p.updated, reverse=True)
        return pages

    def reindex(self) -> dict:
        return reconcile(self.backend, self.store)
