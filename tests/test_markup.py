from wiskill.markup import render_html, extract_wikilinks, plain_summary, clean_snippet_html


def test_extract_wikilinks():
    body = "See [[proyectos/semlix]] and [[notas/x|Nota X]]."
    assert extract_wikilinks(body) == ["proyectos/semlix", "notas/x"]


def test_gfm_features_render():
    html = render_html("~~old~~ and `code`\n\n| a | b |\n|---|---|\n| 1 | 2 |", lambda s: True)
    assert "<del>old</del>" in html
    assert "<table>" in html
    assert "<code>code</code>" in html


def test_fenced_code_gets_syntax_highlighted():
    html = render_html('```python\ndef foo():\n    return 1\n```', lambda s: True)
    assert '<pre><code class="language-python">' in html
    assert '<span class="k">def</span>' in html


def test_fenced_code_unknown_language_falls_back_plain():
    html = render_html('```notalang\nhello\n```', lambda s: True)
    assert '<pre><code class="language-notalang">hello\n</code></pre>' in html


def test_fenced_code_no_language_is_plain():
    html = render_html('```\nhello\n```', lambda s: True)
    assert "<pre><code>hello\n</code></pre>" in html


def test_raw_html_is_escaped():
    html = render_html("<script>alert(1)</script>", lambda s: True)
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_wikilink_existing_vs_missing():
    html = render_html("[[a]] [[b|Bee]]", lambda s: s == "a")
    assert 'href="/a"' in html and 'class="wikilink"' in html
    assert 'href="/b/edit"' in html and "missing" in html
    assert ">Bee<" in html


def test_bare_url_is_autolinked():
    html = render_html("visit https://example.com now", lambda s: True)
    assert '<a href="https://example.com">https://example.com</a>' in html


def test_wikilink_label_with_ampersand_not_double_escaped():
    # Regression: markdown-it already HTML-escapes "&" -> "&amp;" when
    # rendering the paragraph text; re-escaping the captured label turned it
    # into "&amp;amp;", which browsers render as the literal text "&amp;".
    html = render_html("[[a|Web UI & JSON API]]", lambda s: True)
    assert ">Web UI &amp; JSON API<" in html
    assert "&amp;amp;" not in html


def test_children_tag_lists_entries_newest_first():
    children = [("notes/b", "Second", "Jul 08, 2026"), ("notes/a", "First", "Jul 07, 2026")]
    html = render_html("Intro.\n\n{{children}}\n", lambda s: True, children=children)
    assert html.index("Second") < html.index("First")
    assert 'href="/notes/b"' in html and 'href="/notes/a"' in html


def test_children_tag_falls_back_when_empty():
    html = render_html("Intro.\n\n{{children}}\n", lambda s: True, children=[])
    assert "Nothing here yet" in html


def test_plain_summary_strips_children_tag():
    summary = plain_summary("Intro text.\n\n{{children}}\n")
    assert "{{children}}" not in summary
    assert "Intro text" in summary


def test_clean_snippet_html_strips_markdown_without_touching_highlight():
    raw = 'Home\nWelcome to my **<b class="match term0">semantic</b> <b class="match term1">notebook</b>** — a wiki'
    cleaned = clean_snippet_html(raw)
    assert "**" not in cleaned
    assert '<b class="match term0">semantic</b>' in cleaned
    assert '<b class="match term1">notebook</b>' in cleaned


def test_clean_snippet_html_resolves_wikilinks_and_collapses_whitespace():
    raw = "Powered by [[projects/wiskill|wiskill]] on top of\n[[projects/semlix|semlix]]."
    cleaned = clean_snippet_html(raw)
    assert "[[" not in cleaned and "]]" not in cleaned
    assert "wiskill" in cleaned and "semlix" in cleaned
    assert "\n" not in cleaned


def test_clean_snippet_html_no_highlight_tags():
    cleaned = clean_snippet_html("# Home\nJust `code` and *stuff*.")
    assert cleaned == "Home Just code and stuff ."
