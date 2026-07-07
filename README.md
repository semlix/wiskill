# semlix-wiskill

A minimal, DokuWiki-style personal wiki backed by
[semlix](https://github.com/semlix/semlix). Your notes are plain Markdown files
on disk; semlix provides fast **lexical + semantic (hybrid)** search over them.

Two front doors:

- a **web UI + JSON API** (FastAPI, server-rendered, no build step), and
- an **MCP server + Claude Code skill**, so an LLM (Claude or any MCP client)
  can read, write, and search your notes as an ultra-fast embedded backend.

Notes are the source of truth (`.md` files); the semlix index is always
rebuildable from them.

---

## Install (uv)

```bash
cd wiskill
uv venv --python 3.11                        # create .venv
uv pip install -e /path/to/semlix            # semlix as an imported library
uv pip install -e ".[dev,semantic,mcp]"      # wiskill + test/semantic/mcp extras
```

Extras: `semantic` (sentence-transformers for hybrid/semantic search),
`mcp` (the MCP server), `bm25` (the fast bm25s lexical engine), `dev` (pytest).

---

## Quickstart

```bash
export WISKILL_SECRET="$(python -c 'import secrets;print(secrets.token_urlsafe(32))')"
uv run wiskill init                                   # create the wiki + seed page
uv run wiskill user add me --role admin --password 'change-me'
uv run wiskill serve                                  # http://127.0.0.1:8000
```

Open http://127.0.0.1:8000, sign in as `me`, and start writing. The **＋ New**
button asks for a slug (e.g. `projects/semlix`) and opens the visual Markdown
editor.

---

## Configuration (`wiskill.toml`)

Everything is configurable; defaults are fully local and need no database.

```toml
[paths]
pages = "data/pages"        # .md files (source of truth)
index = "data/index"        # semlix index (rebuildable)

[search]
mode = "hybrid"             # lexical | semantic | hybrid
lexical_engine = "core"     # core | bm25
alpha = 0.5                 # semantic weight in hybrid (0 = lexical, 1 = semantic)
fusion = "rrf"              # rrf | linear | dbsf

[semantic]
provider = "sentence-transformers"   # | openai | cohere
model = "all-MiniLM-L6-v2"
vector_store = "numpy"               # numpy | faiss | pgvector

[auth]
users_file = "data/users.json"
apikeys_file = "data/apikeys.json"
session_secret_env = "WISKILL_SECRET"
session_ttl_hours = 168
```

**Search modes**
- `lexical` — keywords only (core engine, with highlighted snippets). No model.
- `semantic` — meaning only (vector search).
- `hybrid` (default) — both, fused with RRF. Local `sentence-transformers` +
  `NumpyVectorStore`, no database.

Point `--config /path/to/wiskill.toml` at any config; relative paths in it
resolve against its own directory. With no `--config`, wiskill uses
`./wiskill.toml` if present, otherwise built-in defaults.

---

## Pages, namespaces, links

- A page is one `.md` file with YAML front-matter (`title`, `tags`, `created`,
  `updated`). The slug is the path without `.md`.
- Namespaces are folders: `projects/semlix`, `notes/2026-07`.
- Link between pages with `[[slug]]` or `[[slug|label]]`. A link to a missing
  page renders dashed/red and takes you to its editor.
- Content is **GitHub-Flavored Markdown** (tables, task lists, strikethrough,
  fenced code, autolinks).

If you edit files outside the app (your editor, git, or an LLM writing files
directly), run `uv run wiskill reindex` to sync the index to disk (it reindexes
changed files and drops deleted ones by content hash).

---

## Secrets (`.env`, not the toml)

Secrets never go in `wiskill.toml` — that file is meant to be versioned, and the
toml only stores the *name* of the secret's env var (`session_secret_env`), not
its value. Set secrets via the environment, or drop them in a **gitignored
`.env`** that wiskill loads automatically (from the config file's directory and
the current directory). A real environment variable always wins over `.env`.

```bash
cp .env.example .env      # then fill it in
```

```ini
# .env  (gitignored — never commit)
WISKILL_SECRET=<python -c "import secrets;print(secrets.token_urlsafe(32))">
WISKILL_API_KEY=<an editor key from `wiskill apikey add`, or leave empty>
```

With `.env` in place you can just run `uv run wiskill serve` / `uv run wiskill
mcp` — no manual `export` each time.

## Authentication

**Roles** (increasing): `reader` < `editor` < `admin`.
Read/search need `reader`; create/edit/delete need `editor`; managing users and
keys needs `admin`.

**Web** — multi-user, session cookie:

```bash
uv run wiskill user add alice --role editor --password '...'
uv run wiskill user list
uv run wiskill user passwd alice --password 'new-pass'   # change a password
uv run wiskill user role  alice --role admin
uv run wiskill user rm    alice
```

Passwords are stored as salted scrypt hashes (never plaintext). The session
cookie is signed with the secret from the `WISKILL_SECRET` environment variable
— set it before `serve`.

**API + MCP** — API key in a header:

```bash
uv run wiskill apikey add my-key --role editor
# → prints the plaintext key ONCE. Copy it now; only its sha256 hash is stored.
uv run wiskill apikey list
uv run wiskill apikey rm  my-key
```

---

## JSON API

Every `/api/*` route requires an API key, sent as **either**
`Authorization: Bearer <key>` **or** `X-API-Key: <key>`. Interactive OpenAPI
docs are at `/docs`.

```bash
KEY=<the key from `wiskill apikey add`>
BASE=http://127.0.0.1:8000

# create / overwrite a page (editor)
curl -X PUT "$BASE/api/pages/notes/idea" -H "Authorization: Bearer $KEY" \
     -H 'Content-Type: application/json' \
     -d '{"title":"Idea","tags":["draft"],"body":"# Hello\n\nSome **notes**."}'

curl "$BASE/api/pages" -H "X-API-Key: $KEY"                 # list slugs
curl "$BASE/api/pages/notes/idea" -H "X-API-Key: $KEY"      # read one page
curl "$BASE/api/search?q=notes" -H "X-API-Key: $KEY"        # search
curl -X DELETE "$BASE/api/pages/notes/idea" -H "X-API-Key: $KEY"
```

Missing/invalid key → `401`; insufficient role → `403`; missing page → `404`.

---

## MCP (use the wiki from an LLM)

The MCP server exposes five tools: `wiki_search`, `wiki_read`, `wiki_write`,
`wiki_list`, `wiki_delete`.

### Web + MCP in one process (recommended)

Run the web UI, JSON API, **and** MCP from a single process so they share one
backend (index + vector store). This is the correct way when using `hybrid`
mode — two separate processes would each keep their own in-memory vector store
and clobber each other's writes.

```bash
uv run wiskill serve --with-mcp             # web at :8000, MCP at :8000/mcp/
```

Register it in Claude Code (note the trailing slash):

```bash
claude mcp add --transport http wiskill http://127.0.0.1:8000/mcp/
```

A page written via MCP is instantly visible in the web UI (and vice-versa),
because both go through the same `WikiService`.


**1. Generate a key (optional).**

```bash
uv run wiskill apikey add claude --role editor    # prints the key once
```

The MCP server reads its key from the `WISKILL_API_KEY` environment variable and
maps it to that key's role. **If no valid key is provided, it falls back to the
`editor` role** — convenient for a trusted, local LLM on your own machine. Set a
key (e.g. a `reader` key) only when you want to restrict what the LLM can do.

**2. Run it.** Pick a transport:

```bash
# stdio (default) — the client launches this process and pipes JSON-RPC.
uv run wiskill mcp                                 # trusted-local: editor role
WISKILL_API_KEY=<key> uv run wiskill mcp           # or with an explicit key/role

# HTTP (Streamable HTTP) — a long-running network server, connect by URL.
uv run wiskill mcp --transport http --host 127.0.0.1 --port 8765
#   → http://127.0.0.1:8765/mcp

# SSE (legacy) — http://host:port/sse
uv run wiskill mcp --transport sse --port 8765
```

> **Security:** MCP does not have raw TCP — "over the network" means HTTP. The
> HTTP/SSE transports are **not authenticated** by wiskill (they use the same
> trusted-local editor fallback), so **bind to `127.0.0.1`** (the default). Do
> not expose them on `0.0.0.0` or a public interface without putting an
> authenticating reverse proxy in front — anyone who can reach the port gets
> write access to your notes.

**3a. Connect via stdio** — add an `.mcp.json` at your project root (or run
`claude mcp add`). Use absolute paths so it works from any directory:

```json
{
  "mcpServers": {
    "wiskill": {
      "command": "/absolute/path/to/wiskill/.venv/bin/wiskill",
      "args": ["--config", "/absolute/path/to/wiskill/wiskill.toml", "mcp"],
      "env": { "WISKILL_API_KEY": "<your editor key, or omit for trusted-local>" }
    }
  }
}
```

**3b. Connect via HTTP** — start the server (`--transport http` above), then
register the URL:

```bash
claude mcp add --transport http wiskill http://127.0.0.1:8765/mcp
# SSE instead:  claude mcp add --transport sse wiskill http://127.0.0.1:8765/sse
```

Then restart Claude Code (or run `/mcp`) to pick up the server. The
`skill/SKILL.md` file documents the tools and conventions for the agent.

> For stdio you can omit the `env` block and instead put `WISKILL_API_KEY` in the
> gitignored `.env` next to `wiskill.toml` — `wiskill mcp` loads it automatically.

> The MCP server speaks JSON-RPC on stdout; model-loading chatter and library
> warnings are redirected to stderr so they can't corrupt the protocol.

---

## CLI reference

```
wiskill [--config PATH] <command>

  init                         create pages dir + a seed page, then reindex
  reindex                      sync the index to the .md files on disk
  serve [--host --port]        run the web UI + JSON API (uvicorn)
  mcp                          run the stdio MCP server
  user add    NAME --role --password
  user passwd NAME --password
  user role   NAME --role
  user list
  user rm     NAME
  apikey add  LABEL --role     (prints the key once)
  apikey list
  apikey rm   LABEL
```

---

## Development

```bash
uv run python -m pytest -q          # full suite (uses a fake embedder; no downloads)
```

Architecture: a pure core (`PageStore` over files + `SearchBackend` over semlix,
orchestrated by `WikiService`) with three thin adapters (FastAPI web+API, MCP
server, CLI). Every write goes through `WikiService`, so the index and disk never
diverge. See `docs/superpowers/specs/` for the design and plan.

## License

BSD-2-Clause.
