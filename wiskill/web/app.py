"""FastAPI web UI (server-rendered Jinja2) + session auth."""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from wiskill.auth import Principal, Role, UserStore
from wiskill.service import PermissionError, WikiService

_HERE = Path(__file__).parent


def create_app(service: WikiService, users: UserStore, config, apikeys=None) -> FastAPI:
    app = FastAPI(title="semlix-wiskill")
    secret = os.environ.get(config.session_secret_env, "dev-insecure-secret")
    app.add_middleware(
        SessionMiddleware, secret_key=secret,
        max_age=config.session_ttl_hours * 3600,
    )
    app.mount("/static", StaticFiles(directory=_HERE / "static"), name="static")
    templates = Jinja2Templates(directory=str(_HERE / "templates"))

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
                request, "login.html", {"error": "Credenciales inválidas"})
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
        return templates.TemplateResponse(
            request, "index.html", {"slugs": service.list_pages(), "user": p})

    @app.get("/search", response_class=HTMLResponse)
    def search(request: Request, q: str = ""):
        p = current(request)
        if p is None:
            return RedirectResponse("/login", status_code=307)
        results = service.search(q) if q else []
        return templates.TemplateResponse(
            request, "search.html", {"q": q, "results": results, "user": p})

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
