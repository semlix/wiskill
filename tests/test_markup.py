from wiskill.markup import render_html, extract_wikilinks


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
