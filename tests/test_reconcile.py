from wiskill.backend import LexicalBackend, reconcile
from wiskill.store import PageStore


def test_reconcile_indexes_new_and_removes_deleted(tmp_path):
    store = PageStore(tmp_path / "pages")
    backend = LexicalBackend(tmp_path / "idx")
    store.write("a", "alpha content")
    store.write("b", "beta content")

    stats = reconcile(backend, store)
    assert stats == {"indexed": 2, "removed": 0}
    assert backend.search("alpha")

    # No changes → nothing reindexed.
    assert reconcile(backend, store) == {"indexed": 0, "removed": 0}

    # Edit one file externally, delete another.
    store.write("a", "alpha UPDATED gamma")
    store.delete("b")
    stats = reconcile(backend, store)
    assert stats == {"indexed": 1, "removed": 1}
    assert backend.search("gamma")
    assert not backend.search("beta")
