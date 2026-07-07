# semlix-wiskill

A minimal, DokuWiki-style personal wiki backed by [semlix](https://github.com/semlix/semlix).
Notes are plain Markdown files on disk; semlix provides fast lexical + semantic
(hybrid) search. Two front doors: a FastAPI web UI + JSON API, and an MCP server
(+ Claude Code skill) so an LLM can read, write, and search your notes.

## Install (uv)

```bash
uv venv --python 3.11                       # .venv
uv pip install -e /path/to/semlix           # semlix as an imported library
uv pip install -e ".[dev,semantic,mcp]"     # wiskill + optional extras
```

## Quickstart

```bash
export WISKILL_SECRET="$(python -c 'import secrets;print(secrets.token_urlsafe(32))')"
wiskill init
wiskill user add me --role admin --password 'changeme'
wiskill serve                     # http://127.0.0.1:8000
```

## Search modes (configurable in `wiskill.toml`)

- `lexical` — keyword only (core engine, with highlights). No embeddings.
- `semantic` — meaning only (vector search).
- `hybrid` (default) — both, fused with RRF. Local `sentence-transformers` +
  `NumpyVectorStore`, no database.

Swap the lexical engine (`core`/`bm25`), embedding provider, and vector store in
config — semlix's protocols make them interchangeable.

## MCP

```bash
wiskill apikey add my-llm --role editor    # prints a key once
WISKILL_API_KEY=<key> wiskill mcp          # stdio MCP server
```

## API

`/api/pages`, `/api/pages/{slug}` (GET/PUT/DELETE), `/api/search?q=` — all require
an API key (`Authorization: Bearer <key>` or `X-API-Key: <key>`). OpenAPI docs at
`/docs`.
