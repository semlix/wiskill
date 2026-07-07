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
from wiskill.service import PermissionError, WikiService

_HERE = Path(__file__).parent


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
    app.add_middleware(
        SessionMiddleware, secret_key=secret,
        max_age=config.session_ttl_hours * 3600,
    )
    app.mount("/static", StaticFiles(directory=_HERE / "static"), name="static")
    templates = Jinja2Templates(directory=str(_HERE / "templates"))
    # Expose the page list to every template (sidebar nav tree).
    templates.env.globals["nav_pages"] = service.list_pages

    # Mount MCP before the catch-all page routes so /mcp isn't captured as a slug.
    if mcp_app is not None:
        app.mount("/mcp", mcp_app)

    if apikeys is not None:
        from wiskill.web.api import build_api_router
        app.include_router(build_api_router(service, apikeys))

    def current(request: Request) -> Principal | None:
        u = request.session.get("user")
        if not u:
            return None
        return Principal(username=u["username"], role=Role(u["role"]))

    @app.get("/login", response_class=HTMLResponse)
    def login_form(request: Request):
        return templates.TemplateResponse(request, "login.html", {"error": None})

    @app.post("/login", response_class=HTMLResponse)
    def login(request: Request, username: str = Form(...), password: str = Form(...)):
        principal = users.authenticate(username, password)
        if principal is None:
            return templates.TemplateResponse(
                request, "login.html", {"error": "Invalid credentials"})
        request.session["user"] = {"username": principal.username, "role": principal.role.value}
        return RedirectResponse("/", status_code=303)

    @app.get("/logout")
    def logout(request: Request):
        request.session.clear()
        return RedirectResponse("/login", status_code=303)

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request):
        p = current(request)
        if p is None:
            return RedirectResponse("/login", status_code=307)
        # Home renders the "index" wiki page (DokuWiki-style start page). If it
        # doesn't exist yet, fall back to a page listing with a create prompt.
        html = service.render("index")
        if html is None:
            return templates.TemplateResponse(
                request, "index.html", {"slugs": service.list_pages(), "user": p})
        return templates.TemplateResponse(request, "page.html", {
            "slug": "index", "html": html, "page": service.get("index"), "user": p})

    @app.get("/search", response_class=HTMLResponse)
    def search(request: Request, q: str = ""):
        p = current(request)
        if p is None:
            return RedirectResponse("/login", status_code=307)
        results = service.search(q) if q else []
        return templates.TemplateResponse(
            request, "search.html", {"q": q, "results": results, "user": p})

    @app.get("/new", response_class=HTMLResponse)
    def new_form(request: Request, error: str | None = None):
        p = current(request)
        if p is None:
            return RedirectResponse("/login", status_code=307)
        return templates.TemplateResponse(request, "new.html", {"user": p, "error": error})

    @app.post("/new")
    def new_create(request: Request, slug: str = Form("")):
        p = current(request)
        if p is None:
            return RedirectResponse("/login", status_code=307)
        slug = slug.strip().strip("/")
        if not slug:
            return templates.TemplateResponse(
                request, "new.html", {"user": p, "error": "Please enter a slug."})
        return RedirectResponse(f"/{slug}/edit", status_code=303)

    @app.get("/{slug:path}/edit", response_class=HTMLResponse)
    def edit_form(request: Request, slug: str):
        p = current(request)
        if p is None:
            return RedirectResponse("/login", status_code=307)
        page = service.get(slug)
        return templates.TemplateResponse(request, "edit.html", {
            "slug": slug, "page": page, "user": p})

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
        p = current(request)
        if p is None:
            return RedirectResponse("/login", status_code=307)
        html = service.render(slug)
        if html is None:
            return RedirectResponse(f"/{slug}/edit", status_code=307)
        page = service.get(slug)
        return templates.TemplateResponse(request, "page.html", {
            "slug": slug, "html": html, "page": page, "user": p})

    return app
