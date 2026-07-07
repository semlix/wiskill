"""JSON API router with API-key auth (Bearer or X-API-Key)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from wiskill.auth import ApiKeyStore, Principal
from wiskill.service import PermissionError


class PageIn(BaseModel):
    title: str | None = None
    tags: list[str] = []
    body: str = ""


def build_api_router(service, apikeys: ApiKeyStore) -> APIRouter:
    router = APIRouter(prefix="/api")

    def principal(authorization: str | None = Header(None),
                  x_api_key: str | None = Header(None)) -> Principal:
        key = None
        if authorization and authorization.lower().startswith("bearer "):
            key = authorization[7:].strip()
        elif x_api_key:
            key = x_api_key.strip()
        p = apikeys.verify(key) if key else None
        if p is None:
            raise HTTPException(status_code=401, detail="invalid or missing API key")
        return p

    def _page_json(page):
        return {"slug": page.slug, "title": page.title, "tags": page.tags,
                "created": page.created.isoformat(), "updated": page.updated.isoformat(),
                "body": page.body}

    @router.get("/pages")
    def list_pages(p: Principal = Depends(principal)):
        return {"slugs": service.list_pages()}

    @router.get("/pages/{slug:path}")
    def get_page(slug: str, p: Principal = Depends(principal)):
        page = service.get(slug)
        if page is None:
            raise HTTPException(status_code=404, detail="not found")
        return _page_json(page)

    @router.put("/pages/{slug:path}")
    def put_page(slug: str, body: PageIn, p: Principal = Depends(principal)):
        try:
            page = service.save(slug, body.body, title=body.title, tags=body.tags, principal=p)
        except PermissionError:
            raise HTTPException(status_code=403, detail="editor role required")
        return _page_json(page)

    @router.delete("/pages/{slug:path}")
    def delete_page(slug: str, p: Principal = Depends(principal)):
        try:
            deleted = service.remove(slug, principal=p)
        except PermissionError:
            raise HTTPException(status_code=403, detail="editor role required")
        return {"deleted": deleted}

    @router.get("/search")
    def search(q: str, limit: int = 10, p: Principal = Depends(principal)):
        results = service.search(q, limit=limit)
        return {"results": [{"slug": r.slug, "title": r.title, "score": r.score,
                             "snippet": r.snippet} for r in results]}

    return router
