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

    def render(self, slug: str) -> str | None:
        page = self.store.read(slug)
        if page is None:
            return None
        return render_html(page.body, self.store.exists)

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

    def reindex(self) -> dict:
        return reconcile(self.backend, self.store)
