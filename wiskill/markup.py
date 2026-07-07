"""Markdown (GFM) + [[wikilink]] rendering."""
from __future__ import annotations

import re
from html import escape
from typing import Callable

from markdown_it import MarkdownIt
from mdit_py_plugins.tasklists import tasklists_plugin

_WIKILINK = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")

# GFM: tables + strikethrough + linkify (bare URL autolinks) enabled
# explicitly on the "commonmark" base; tasklists via plugin. Raw HTML
# disabled (html=False) to prevent stored XSS.
#
# The "commonmark" preset disables the linkify rule by default even when
# the `linkify: True` option is set on the option dict, so it must also be
# turned on explicitly via .enable(["linkify"]) — this requires the
# linkify-it-py package to be installed.
#
# markdown-it-py's built-in strikethrough rule renders <s>...</s>, but GFM
# (https://github.github.com/gfm/#strikethrough-extension-) specifies
# <del>...</del>; override the render rules to match GFM output.
_md = (
    MarkdownIt("commonmark", {"html": False, "linkify": True})
    .enable(["table", "strikethrough", "linkify"])
    .use(tasklists_plugin)
)
_md.add_render_rule("s_open", lambda self, tokens, idx, options, env: "<del>")
_md.add_render_rule("s_close", lambda self, tokens, idx, options, env: "</del>")


def extract_wikilinks(body: str) -> list[str]:
    seen: list[str] = []
    for m in _WIKILINK.finditer(body):
        slug = m.group(1).strip()
        if slug not in seen:
            seen.append(slug)
    return seen


def _replace_wikilinks(body: str, exists: Callable[[str], bool]) -> str:
    def repl(m: re.Match) -> str:
        slug = m.group(1).strip()
        label = (m.group(2) or slug).strip()
        if exists(slug):
            return f'<a href="/{escape(slug)}" class="wikilink">{escape(label)}</a>'
        return f'<a href="/{escape(slug)}/edit" class="wikilink missing">{escape(label)}</a>'
    return _WIKILINK.sub(repl, body)


def render_html(body: str, exists: Callable[[str], bool]) -> str:
    # Resolve wikilinks to HTML anchors *after* markdown rendering, so
    # html=False still blocks user-authored tags. [[...]] tokens are plain
    # text to markdown-it and pass through untouched, so the regex finds
    # them intact in the rendered HTML.
    html = _md.render(body)
    return _replace_wikilinks(html, exists)
