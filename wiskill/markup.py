"""Markdown (GFM) + [[wikilink]] rendering."""
from __future__ import annotations

import re
from typing import Callable

from markdown_it import MarkdownIt
from mdit_py_plugins.tasklists import tasklists_plugin

_WIKILINK = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")
_CHILDREN_TAG = re.compile(r"^\{\{children\}\}[ \t]*$", re.MULTILINE)

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


def _strip_markdown_noise(text: str) -> str:
    """Wikilinks, {{children}}, markdown punctuation, and link targets -> plain
    text (whitespace not yet collapsed). Shared by plain_summary and
    clean_snippet_html."""
    text = _WIKILINK.sub(lambda m: (m.group(2) or m.group(1)).strip(), text)
    text = _CHILDREN_TAG.sub("", text)                  # {{children}} placeholder
    text = re.sub(r"[#>*_`~\[\]!]", " ", text)          # markdown punctuation
    text = re.sub(r"\((?:https?://)?[^)]*\)", " ", text)  # link targets
    return text


def plain_summary(body: str, limit: int = 155) -> str:
    """A plain-text one-line summary of a Markdown body, for meta descriptions.
    Strips common Markdown/wikilink syntax and collapses whitespace."""
    text = re.sub(r"\s+", " ", _strip_markdown_noise(body)).strip()
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0] + "…"
    return text


_HIGHLIGHT_TAG = re.compile(r"<b\b[^>]*>.*?</b>", re.DOTALL)


def clean_snippet_html(snippet: str) -> str:
    """Clean a search-result snippet for display. The search backend's
    highlighter already HTML-escapes the surrounding text and wraps matched
    query terms in `<b class="match termN">...</b>` spans; this strips
    Markdown/wikilink syntax from the text around those spans without
    touching the spans themselves."""
    pieces = _HIGHLIGHT_TAG.split(snippet)
    tags = _HIGHLIGHT_TAG.findall(snippet)
    out = []
    for i, piece in enumerate(pieces):
        out.append(_strip_markdown_noise(piece))
        if i < len(tags):
            out.append(tags[i])
    return re.sub(r"\s+", " ", "".join(out)).strip()


def extract_wikilinks(body: str) -> list[str]:
    seen: list[str] = []
    for m in _WIKILINK.finditer(body):
        slug = m.group(1).strip()
        if slug not in seen:
            seen.append(slug)
    return seen


def _replace_wikilinks(body: str, exists: Callable[[str], bool]) -> str:
    # `body` here is already-rendered HTML (from _md.render), so any special
    # characters in the captured slug/label are already HTML-entity-escaped by
    # markdown-it. Re-escaping them would double-escape (e.g. "&" -> "&amp;"
    # -> "&amp;amp;", which browsers then show as the literal text "&amp;").
    def repl(m: re.Match) -> str:
        slug = m.group(1).strip()
        label = (m.group(2) or slug).strip()
        if exists(slug):
            return f'<a href="/{slug}" class="wikilink">{label}</a>'
        return f'<a href="/{slug}/edit" class="wikilink missing">{label}</a>'
    return _WIKILINK.sub(repl, body)


def _expand_children_tag(body: str, children: list[tuple[str, str, str]]) -> str:
    """Replace a standalone `{{children}}` line with a markdown bullet list
    of (slug, title, updated_display) — before markdown rendering, so the
    generated [[wikilinks]] and formatting flow through the normal pipeline
    instead of needing separate HTML-escaping rules."""
    if not _CHILDREN_TAG.search(body):
        return body
    if children:
        listing = "\n".join(
            f"- [[{slug}|{title}]] — updated {updated}" for slug, title, updated in children)
    else:
        listing = "_Nothing here yet._"
    return _CHILDREN_TAG.sub(listing, body)


def render_html(body: str, exists: Callable[[str], bool],
                children: list[tuple[str, str, str]] | None = None) -> str:
    # Resolve wikilinks to HTML anchors *after* markdown rendering, so
    # html=False still blocks user-authored tags. [[...]] tokens are plain
    # text to markdown-it and pass through untouched, so the regex finds
    # them intact in the rendered HTML.
    body = _expand_children_tag(body, children or [])
    html = _md.render(body)
    return _replace_wikilinks(html, exists)
