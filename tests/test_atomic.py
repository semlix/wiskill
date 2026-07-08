from wiskill._atomic import atomic_write_text


def test_writes_content(tmp_path):
    p = tmp_path / "data.json"
    atomic_write_text(p, "hello")
    assert p.read_text() == "hello"


def test_overwrites_existing_file(tmp_path):
    p = tmp_path / "data.json"
    p.write_text("old")
    atomic_write_text(p, "new")
    assert p.read_text() == "new"


def test_no_leftover_temp_files(tmp_path):
    p = tmp_path / "data.json"
    atomic_write_text(p, "hello")
    assert list(tmp_path.iterdir()) == [p]
