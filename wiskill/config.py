"""Configuration loading for wiskill (wiskill.toml → WiskillConfig)."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WiskillConfig:
    pages_dir: Path = Path("data/pages")
    index_dir: Path = Path("data/index")
    mode: str = "hybrid"                 # lexical | semantic | hybrid
    lexical_engine: str = "core"         # core | bm25
    alpha: float = 0.5
    fusion: str = "rrf"                  # rrf | linear | dbsf
    provider: str = "sentence-transformers"
    model: str = "all-MiniLM-L6-v2"
    vector_store: str = "numpy"          # numpy | faiss | pgvector
    users_file: Path = Path("data/users.json")
    apikeys_file: Path = Path("data/apikeys.json")
    session_secret_env: str = "WISKILL_SECRET"
    session_ttl_hours: int = 168
    public_read: bool = False   # allow anonymous view + search (no login to read)
    site_url: str = ""   # public base URL (e.g. "https://wiskill.barrahome.org"),
    # used to build absolute URLs for /sitemap.xml and the /robots.txt
    # Sitemap: line. Empty => sitemap.xml is disabled (404).
    mcp_require_key: bool = False  # require an API key on /mcp when served over HTTP
    mcp_allowed_hosts: tuple[str, ...] = ()  # Host headers the MCP transport accepts
    # (e.g. your public domain). Empty = disable the MCP SDK's DNS-rebinding
    # Host check entirely — fine here since mcp_require_key already gates /mcp.
    private_namespaces: tuple[str, ...] = ()  # top-level namespaces (e.g. "notes",
    # "ideas") that require a logged-in account even when public_read is on.
    # Any authenticated role qualifies; only true anonymous guests are blocked.


def load_config(path: str | Path | None = None) -> WiskillConfig:
    """Load config from a TOML file. Missing file → all defaults.

    Relative paths inside the file resolve against the file's directory.
    """
    defaults = WiskillConfig()
    if path is None:
        return defaults
    path = Path(path)
    if not path.exists():
        return defaults

    with path.open("rb") as fh:
        data = tomllib.load(fh)

    base = path.resolve().parent
    paths = data.get("paths", {})
    search = data.get("search", {})
    semantic = data.get("semantic", {})
    auth = data.get("auth", {})
    web = data.get("web", {})

    def rel(value: str | None, default: Path) -> Path:
        if value is None:
            return (base / default).resolve() if not default.is_absolute() else default
        p = Path(value)
        return p if p.is_absolute() else (base / p).resolve()

    return WiskillConfig(
        pages_dir=rel(paths.get("pages"), defaults.pages_dir),
        index_dir=rel(paths.get("index"), defaults.index_dir),
        mode=search.get("mode", defaults.mode),
        lexical_engine=search.get("lexical_engine", defaults.lexical_engine),
        alpha=float(search.get("alpha", defaults.alpha)),
        fusion=search.get("fusion", defaults.fusion),
        provider=semantic.get("provider", defaults.provider),
        model=semantic.get("model", defaults.model),
        vector_store=semantic.get("vector_store", defaults.vector_store),
        users_file=rel(auth.get("users_file"), defaults.users_file),
        apikeys_file=rel(auth.get("apikeys_file"), defaults.apikeys_file),
        session_secret_env=auth.get("session_secret_env", defaults.session_secret_env),
        session_ttl_hours=int(auth.get("session_ttl_hours", defaults.session_ttl_hours)),
        public_read=bool(web.get("public_read", defaults.public_read)),
        site_url=str(web.get("site_url", defaults.site_url)),
        mcp_require_key=bool(web.get("mcp_require_key", defaults.mcp_require_key)),
        mcp_allowed_hosts=tuple(web.get("mcp_allowed_hosts", defaults.mcp_allowed_hosts)),
        private_namespaces=tuple(web.get("private_namespaces", defaults.private_namespaces)),
    )
