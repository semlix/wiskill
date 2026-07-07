"""wiskill command-line interface."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from wiskill.auth import ApiKeyStore, Role, UserStore
from wiskill.backend import build_backend
from wiskill.config import load_config
from wiskill.service import WikiService
from wiskill.store import PageStore


def _default_config_path() -> str | None:
    p = Path("wiskill.toml")
    return str(p) if p.exists() else None


def _service(config):
    return WikiService(PageStore(config.pages_dir), build_backend(config))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="wiskill")
    parser.add_argument("--config", default=_default_config_path())
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init")
    sub.add_parser("reindex")
    sub.add_parser("mcp")
    serve = sub.add_parser("serve")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)

    user = sub.add_parser("user").add_subparsers(dest="ucmd", required=True)
    for name in ("add", "passwd"):
        pp = user.add_parser(name); pp.add_argument("username")
        pp.add_argument("--password", required=True)
        if name == "add":
            pp.add_argument("--role", default="editor")
    ur = user.add_parser("role"); ur.add_argument("username"); ur.add_argument("--role", required=True)
    user.add_parser("list")
    urm = user.add_parser("rm"); urm.add_argument("username")

    key = sub.add_parser("apikey").add_subparsers(dest="kcmd", required=True)
    ka = key.add_parser("add"); ka.add_argument("label"); ka.add_argument("--role", default="editor")
    key.add_parser("list")
    krm = key.add_parser("rm"); krm.add_argument("label")

    args = parser.parse_args(argv)
    config = load_config(args.config)

    if args.cmd == "init":
        store = PageStore(config.pages_dir)
        if not store.exists("index"):
            store.write(
                "index",
                "# Welcome to wiskill\n\n"
                "This is your home page. Edit it, or create new pages.\n\n"
                "- Link to other notes with `[[slug]]` or `[[slug|label]]`.\n"
                "- Organize with namespaces: `projects/semlix`, `notes/2026-07`.\n"
                "- Search combines keywords **and** meaning (hybrid search).\n",
                title="Welcome",
            )
        _service(config).reindex()
        print(f"initialized wiki at {config.pages_dir}")
        return 0

    if args.cmd == "reindex":
        stats = _service(config).reindex()
        print(f"reindex: indexed={stats['indexed']} removed={stats['removed']}")
        return 0

    if args.cmd == "mcp":
        from wiskill.mcp.server import run_stdio
        run_stdio(args.config)
        return 0

    if args.cmd == "serve":
        import uvicorn
        from wiskill.web.app import create_app
        service = _service(config)
        service.reindex()
        users = UserStore(config.users_file)
        keys = ApiKeyStore(config.apikeys_file)
        app = create_app(service, users, config, apikeys=keys)
        uvicorn.run(app, host=args.host, port=args.port)
        return 0

    if args.cmd == "user":
        us = UserStore(config.users_file)
        if args.ucmd == "add":
            us.add(args.username, args.password, Role(args.role)); print(f"user {args.username} added")
        elif args.ucmd == "passwd":
            us.set_password(args.username, args.password); print("password updated")
        elif args.ucmd == "role":
            us.set_role(args.username, Role(args.role)); print("role updated")
        elif args.ucmd == "list":
            for u, r in us.list_users(): print(f"{u}\t{r.value}")
        elif args.ucmd == "rm":
            print("removed" if us.remove(args.username) else "no such user")
        return 0

    if args.cmd == "apikey":
        ks = ApiKeyStore(config.apikeys_file)
        if args.kcmd == "add":
            k = ks.create(args.label, Role(args.role))
            print(f"API key for {args.label} ({args.role}) — store it now, shown once:")
            print(k)
        elif args.kcmd == "list":
            for label, r in ks.list_keys(): print(f"{label}\t{r.value}")
        elif args.kcmd == "rm":
            print("removed" if ks.remove(args.label) else "no such key")
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
