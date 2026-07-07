"""MCP server exposing the wiki to an LLM. Tool logic lives in WikiTools
(dependency-free, unit-testable); build_mcp/run_stdio need the `mcp` package."""
from __future__ import annotations

import os
from pathlib import Path

from wiskill.auth import ApiKeyStore, Principal, Role


class WikiTools:
    def __init__(self, service, principal: Principal):
        self.service = service
        self.principal = principal

    def wiki_search(self, query: str, limit: int = 10) -> list[dict]:
        return [{"slug": r.slug, "title": r.title, "score": r.score, "snippet": r.snippet}
                for r in self.service.search(query, limit=limit)]

    def wiki_read(self, slug: str) -> dict | None:
        page = self.service.get(slug)
        if page is None:
            return None
        return {"slug": page.slug, "title": page.title, "tags": page.tags,
                "updated": page.updated.isoformat(), "body": page.body}

    def wiki_write(self, slug: str, content: str, title: str | None = None,
                   tags: list[str] | None = None) -> dict:
        page = self.service.save(slug, content, title=title, tags=tags or [],
                                 principal=self.principal)
        return {"slug": page.slug, "title": page.title, "updated": page.updated.isoformat()}

    def wiki_list(self, namespace: str | None = None) -> list[str]:
        return self.service.list_pages(namespace)

    def wiki_delete(self, slug: str) -> bool:
        return self.service.remove(slug, principal=self.principal)

    def wiki_reindex(self) -> dict:
        """Sync the index to on-disk .md files (for out-of-band edits). Safe:
        reconciles by content hash, never deletes the index. Editor role."""
        from wiskill.auth import Role
        from wiskill.service import PermissionError
        if not self.principal.role.allows(Role.EDITOR):
            raise PermissionError("reindex requires editor role")
        return self.service.reindex()


def build_mcp(service, principal: Principal, host: str = "127.0.0.1", port: int = 8765,
              stateless: bool = False, http_path: str = "/mcp"):
    """Build the FastMCP server. For mounting inside another ASGI app (e.g. the
    web server), pass ``stateless=True`` and ``http_path='/'`` and mount its
    ``streamable_http_app()`` under a prefix."""
    from mcp.server.fastmcp import FastMCP
    tools = WikiTools(service, principal)
    mcp = FastMCP("wiskill", host=host, port=port,
                  stateless_http=stateless, streamable_http_path=http_path)

    @mcp.tool()
    def wiki_search(query: str, limit: int = 10) -> list[dict]:
        """Search the wiki (lexical + semantic). Returns slug, title, score, snippet."""
        return tools.wiki_search(query, limit)

    @mcp.tool()
    def wiki_read(slug: str) -> dict | None:
        """Read one wiki page by slug (e.g. 'notas/reunion'). None if absent."""
        return tools.wiki_read(slug)

    @mcp.tool()
    def wiki_write(slug: str, content: str, title: str | None = None,
                   tags: list[str] | None = None) -> dict:
        """Create or overwrite a wiki page (Markdown body). Requires editor role."""
        return tools.wiki_write(slug, content, title, tags)

    @mcp.tool()
    def wiki_list(namespace: str | None = None) -> list[str]:
        """List page slugs, optionally under a namespace prefix."""
        return tools.wiki_list(namespace)

    @mcp.tool()
    def wiki_delete(slug: str) -> bool:
        """Delete a wiki page by slug. Requires editor role."""
        return tools.wiki_delete(slug)

    @mcp.tool()
    def wiki_reindex() -> dict:
        """Sync the search index to the on-disk Markdown files (use after files
        were edited outside the app). Returns {indexed, removed}. Editor role."""
        return tools.wiki_reindex()

    return mcp


def _resolve_principal(config) -> Principal:
    key = os.environ.get("WISKILL_API_KEY")
    if key and Path(config.apikeys_file).exists():
        p = ApiKeyStore(config.apikeys_file).verify(key)
        if p is not None:
            return p
    # Trusted-local fallback: no key configured → editor. Documented in SKILL.md.
    return Principal("local", Role.EDITOR)


# Map our friendly transport names to FastMCP's.
_TRANSPORTS = {"stdio": "stdio", "http": "streamable-http", "sse": "sse"}


def run_server(config_path: str | None = None, transport: str = "stdio",
               host: str = "127.0.0.1", port: int = 8765) -> None:
    """Run the MCP server over the chosen transport.

    - ``stdio``: launched by a client (Claude Code); speaks JSON-RPC on stdout.
    - ``http``: Streamable HTTP at ``http://host:port/mcp`` (the network option).
    - ``sse``: legacy Server-Sent Events at ``http://host:port/sse``.
    """
    import contextlib
    import sys

    from wiskill._setup import quiet_ml_noise
    quiet_ml_noise()

    if transport not in _TRANSPORTS:
        raise ValueError(f"unknown transport: {transport!r} (use stdio|http|sse)")

    from wiskill.config import load_config
    from wiskill.service import WikiService
    from wiskill.store import PageStore
    from wiskill.backend import build_backend

    config = load_config(config_path)

    def _build():
        service = WikiService(PageStore(config.pages_dir), build_backend(config))
        service.reindex()  # sync any external edits before serving
        return service

    # For stdio, stdout carries the JSON-RPC protocol, so any model/loader
    # chatter printed there would corrupt it — redirect it to stderr while the
    # backend loads. HTTP/SSE carry the protocol over the socket, so normal
    # stdout logging is fine (and useful).
    if transport == "stdio":
        with contextlib.redirect_stdout(sys.stderr):
            service = _build()
    else:
        service = _build()

    principal = _resolve_principal(config)
    mcp = build_mcp(service, principal, host=host, port=port)
    try:
        mcp.run(transport=_TRANSPORTS[transport])
    except KeyboardInterrupt:
        pass  # Ctrl-C is the normal way to stop the server; exit quietly.


def run_stdio(config_path: str | None = None) -> None:
    """Backwards-compatible stdio entrypoint."""
    run_server(config_path, transport="stdio")
