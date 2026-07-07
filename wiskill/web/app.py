"""FastAPI web UI (server-rendered Jinja2) + session auth."""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from wiskill.auth import Principal, Role, UserStore
from wiskill.markup import plain_summary
from wiskill.service import PermissionError, WikiService

_HERE = Path(__file__).parent
_SITE_DESC = ("A personal semantic wiki — Markdown notes with fast hybrid "
              "lexical + semantic search.")


def _nav_sort_key(name: str) -> tuple:
    """'index' always first, everything else alphabetical."""
    return (name != "index", name)


def build_nav_tree(slugs: list[str]) -> dict:
    """Nest a flat slug list into
    {name: {"slug": str|None, "children": {...}, "count": int}},
    ordered depth-first with 'index' pinned first at every level. A node's
    "slug" is set only if that exact path is itself a page (namespaces like
    'projects' are usually also pages); pure intermediate segments get
    slug=None and render as a plain (non-linking) label. "count" is the
    total number of real pages in that node's subtree, itself included."""
    root: dict = {}
    for slug in slugs:
        parts = slug.split("/")
        node = root
        for i, part in enumerate(parts):
            entry = node.setdefault(part, {"slug": None, "children": {}})
            if i == len(parts) - 1:
                entry["slug"] = slug
            node = entry["children"]

    def finalize(d: dict) -> dict:
        ordered = {k: d[k] for k in sorted(d.keys(), key=_nav_sort_key)}
        for v in ordered.values():
            v["children"] = finalize(v["children"])
            v["count"] = (1 if v["slug"] else 0) + sum(
                c["count"] for c in v["children"].values())
        return ordered

    return finalize(root)


def create_app(service: WikiService, users: UserStore, config, apikeys=None,
               mcp_server=None) -> FastAPI:
    # When an MCP server is provided, mount it at /mcp in the same process so it
    # shares this WikiService (and its in-memory index/vector store). Its ASGI
    # lifespan must run, so thread it through the FastAPI app's lifespan.
    mcp_app = mcp_server.streamable_http_app() if mcp_server is not None else None

    lifespan = None
    if mcp_app is not None:
        @asynccontextmanager
        async def lifespan(_app):  # noqa: F811
            async with mcp_app.router.lifespan_context(_app):
                yield

    app = FastAPI(title="semlix-wiskill", lifespan=lifespan)
    secret = os.environ.get(config.session_secret_env, "dev-insecure-secret")

    # Gate the MCP endpoint with an API key when configured (it is otherwise
    # unauthenticated — a trusted-local editor). Runs before routing; only
    # affects /mcp paths.
    if getattr(config, "mcp_require_key", False) and apikeys is not None:
        from fastapi.responses import JSONResponse

        @app.middleware("http")
        async def _require_mcp_key(request: Request, call_next):
            if request.url.path.startswith("/mcp"):
                auth = request.headers.get("authorization", "")
                key = auth[7:].strip() if auth.lower().startswith("bearer ") \
                    else request.headers.get("x-api-key", "").strip()
                principal = apikeys.verify(key) if key else None
                if principal is None or not principal.role.allows(Role.EDITOR):
                    return JSONResponse({"detail": "invalid or missing API key"}, status_code=401)
            return await call_next(request)

    app.add_middleware(
        SessionMiddleware, secret_key=secret,
        max_age=config.session_ttl_hours * 3600,
    )
    app.mount("/static", StaticFiles(directory=_HERE / "static"), name="static")
    templates = Jinja2Templates(directory=str(_HERE / "templates"))

    def is_private(slug: str) -> bool:
        top = slug.split("/", 1)[0]
        return top in config.private_namespaces

    def nav_pages_for(authed: bool) -> list[str]:
        """Sidebar page list. Anonymous guests never see private-namespace
        slugs — not just their content, their existence."""
        slugs = service.list_pages()
        return slugs if authed else [s for s in slugs if not is_private(s)]

    def nav_tree_for(authed: bool) -> dict:
        """Nested, collapsible sidebar tree (see build_nav_tree) over the
        same authed-filtered page list as nav_pages_for."""
        return build_nav_tree(nav_pages_for(authed))

    # Default (unauthenticated) globals for templates rendered outside a
    # route (e.g. an error page); routes override with the request-scoped
    # version via _common()/explicit context.
    templates.env.globals["nav_pages"] = lambda: nav_pages_for(False)
    templates.env.globals["nav_tree"] = lambda: nav_tree_for(False)

    # Mount MCP before the catch-all page routes so /mcp isn't captured as a slug.
    if mcp_app is not None:
        app.mount("/mcp", mcp_app)

    if apikeys is not None:
        from wiskill.web.api import build_api_router
        app.include_router(build_api_router(service, apikeys))

    def current(request: Request) -> Principal | None:
        """The logged-in user, or None."""
        u = request.session.get("user")
        if not u:
            return None
        return Principal(username=u["username"], role=Role(u["role"]))

    def viewer(request: Request) -> tuple[Principal | None, bool]:
        """Who is viewing, and whether they're authenticated. When public_read
        is on, anonymous visitors get an implicit READER (view + search only)."""
        p = current(request)
        if p is not None:
            return p, True
        if config.public_read:
            return Principal(username="guest", role=Role.READER), False
        return None, False

    @app.get("/login", response_class=HTMLResponse)
    def login_form(request: Request):
        return templates.TemplateResponse(request, "login.html",
                                          {"error": None, "meta_title": "Sign in"})

    @app.post("/login", response_class=HTMLResponse)
    def login(request: Request, username: str = Form(...), password: str = Form(...)):
        principal = users.authenticate(username, password)
        if principal is None:
            return templates.TemplateResponse(
                request, "login.html", {"error": "Invalid credentials", "meta_title": "Sign in"})
        request.session["user"] = {"username": principal.username, "role": principal.role.value}
        return RedirectResponse("/", status_code=303)

    @app.get("/logout")
    def logout(request: Request):
        request.session.clear()
        return RedirectResponse("/login", status_code=303)

    def _common(p, authed):
        return {"user": p, "authenticated": authed, "public": config.public_read,
                "nav_pages": (lambda: nav_pages_for(authed)),
                "nav_tree": (lambda: nav_tree_for(authed))}

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request):
        p, authed = viewer(request)
        if p is None:
            return RedirectResponse("/login", status_code=307)
        # Home renders the "index" wiki page (DokuWiki-style start page). If it
        # doesn't exist yet, fall back to a page listing with a create prompt.
        html = service.render("index")
        if html is None:
            return templates.TemplateResponse(request, "index.html", {
                "slugs": nav_pages_for(authed), "meta_title": "Home",
                "meta_description": _SITE_DESC, **_common(p, authed)})
        page = service.get("index")
        return templates.TemplateResponse(request, "page.html", {
            "slug": "index", "html": html, "page": page,
            "meta_title": page.title, "meta_description": plain_summary(page.body),
            **_common(p, authed)})

    @app.get("/search", response_class=HTMLResponse)
    def search(request: Request, q: str = ""):
        p, authed = viewer(request)
        if p is None:
            return RedirectResponse("/login", status_code=307)
        results = service.search(q) if q else []
        if not authed:
            results = [r for r in results if not is_private(r.slug)]
        return templates.TemplateResponse(request, "search.html", {
            "q": q, "results": results,
            "meta_title": (f"Search: {q}" if q else "Search"),
            "meta_description": (f"Search results for “{q}”." if q else _SITE_DESC),
            **_common(p, authed)})

    @app.get("/new", response_class=HTMLResponse)
    def new_form(request: Request, error: str | None = None):
        p = current(request)
        if p is None:
            return RedirectResponse("/login", status_code=307)
        return templates.TemplateResponse(request, "new.html",
                                          {"user": p, "error": error, "meta_title": "New page",
                                           "nav_pages": (lambda: nav_pages_for(True)),
                 "nav_tree": (lambda: nav_tree_for(True))})

    @app.post("/new")
    def new_create(request: Request, slug: str = Form("")):
        p = current(request)
        if p is None:
            return RedirectResponse("/login", status_code=307)
        slug = slug.strip().strip("/")
        if not slug:
            return templates.TemplateResponse(
                request, "new.html",
                {"user": p, "error": "Please enter a slug.", "meta_title": "New page",
                 "nav_pages": (lambda: nav_pages_for(True)),
                 "nav_tree": (lambda: nav_tree_for(True))})
        return RedirectResponse(f"/{slug}/edit", status_code=303)

    @app.get("/{slug:path}/edit", response_class=HTMLResponse)
    def edit_form(request: Request, slug: str):
        p = current(request)
        if p is None:
            return RedirectResponse("/login", status_code=307)
        page = service.get(slug)
        return templates.TemplateResponse(request, "edit.html", {
            "slug": slug, "page": page, "user": p,
            "meta_title": f"Edit {slug}",
            "nav_pages": (lambda: nav_pages_for(True)),
                 "nav_tree": (lambda: nav_tree_for(True))})

    @app.post("/{slug:path}/delete")
    def delete(request: Request, slug: str):
        p = current(request)
        if p is None:
            return RedirectResponse("/login", status_code=307)
        try:
            service.remove(slug, principal=p)
        except PermissionError:
            return HTMLResponse("Forbidden", status_code=403)
        return RedirectResponse("/", status_code=303)

    @app.post("/{slug:path}")
    def save(request: Request, slug: str,
             title: str = Form(""), tags: str = Form(""), body: str = Form("")):
        p = current(request)
        if p is None:
            return RedirectResponse("/login", status_code=307)
        taglist = [t.strip() for t in tags.split(",") if t.strip()]
        try:
            service.save(slug, body, title=title or None, tags=taglist, principal=p)
        except PermissionError:
            return HTMLResponse("Forbidden", status_code=403)
        return RedirectResponse(f"/{slug}", status_code=303)

    @app.get("/{slug:path}", response_class=HTMLResponse)
    def view(request: Request, slug: str):
        p, authed = viewer(request)
        if p is None:
            return RedirectResponse("/login", status_code=307)
        if is_private(slug) and not authed:
            # Don't reveal whether a private page exists to a guest — same
            # redirect as "not logged in at all".
            return RedirectResponse("/login", status_code=307)
        html = service.render(slug)
        if html is None:
            # Missing page → editors go to the editor (which prompts login for
            # anonymous/guest viewers).
            return RedirectResponse(f"/{slug}/edit", status_code=307)
        page = service.get(slug)
        return templates.TemplateResponse(request, "page.html", {
            "slug": slug, "html": html, "page": page,
            "meta_title": page.title, "meta_description": plain_summary(page.body),
            **_common(p, authed)})

    return app
