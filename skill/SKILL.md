---
name: wiskill
description: Read, write, and search the user's personal wiki (semlix-wiskill) via its MCP server. Use when the user asks to look something up in their notes, save a note, or organize knowledge.
---

# wiskill — personal wiki over MCP

The wiki is Markdown files searchable with semlix (lexical + semantic). Talk to
it through the `wiskill` MCP server's tools.

## Tools

- `wiki_search(query, limit=10)` — hybrid search; returns slug, title, score, snippet.
- `wiki_read(slug)` — full page (e.g. `notas/reunion`); None if it doesn't exist.
- `wiki_write(slug, content, title?, tags?)` — create/overwrite (Markdown). Editor role.
- `wiki_list(namespace?)` — list slugs, optionally under a namespace prefix.
- `wiki_delete(slug)` — delete a page. Editor role.

## Conventions

- **Search before writing** so you extend an existing page instead of duplicating.
- Slugs are lowercase paths with `/` as namespace separator: `proyectos/semlix`,
  `notas/reuniones/2026-07`. Segments allow `[A-Za-z0-9._-]` only.
- Link between pages with `[[slug]]` or `[[slug|label]]`.
- Content is GitHub-Flavored Markdown. Keep pages focused; split large topics
  into namespaced sub-pages and link them.

## Setup

Configure the MCP server (stdio):

    command: wiskill
    args: ["mcp"]
    env: { WISKILL_API_KEY: "<an editor key from `wiskill apikey add`>" }
