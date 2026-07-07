from wiskill.markup import render_html, extract_wikilinks, plain_summary


def test_extract_wikilinks():
    body = "See [[proyectos/semlix]] and [[notas/x|Nota X]]."
    assert extract_wikilinks(body) == ["proyectos/semlix", "notas/x"]


def test_gfm_features_render():
    html = render_html("~~old~~ and `code`\n\n| a | b |\n|---|---|\n| 1 | 2 |", lambda s: True)
    assert "<del>old</del>" in html
    assert "<table>" in html
    assert "<code>code</code>" in html


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
