import numpy as np
import pytest


class FakeEmbeddingProvider:
    """Deterministic hashing embedder — no model download, stable vectors."""

    def __init__(self, dimension: int = 32):
        self._dim = dimension

    @property
    def dimension(self) -> int:
        return self._dim

    def encode(self, texts, **kwargs):
        vecs = np.zeros((len(texts), self._dim), dtype=np.float32)
        for i, text in enumerate(texts):
            for tok in str(text).lower().split():
                vecs[i, hash(tok) % self._dim] += 1.0
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return vecs / norms


@pytest.fixture
def fake_provider():
    return FakeEmbeddingProvider()
