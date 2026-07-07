"""Environment setup shared by the CLI/MCP entrypoints."""
from __future__ import annotations

import os
import warnings
from pathlib import Path


def load_env_file(config_path: str | None = None) -> list[str]:
    """Load secrets from a gitignored ``.env`` (KEY=VALUE lines) into the
    environment, so they never have to live in the committed ``wiskill.toml``.

    Looks next to the config file (the project root) and in the current
    directory. A real environment variable always wins over the file (we only
    ``setdefault``). Returns the paths that were loaded. Dependency-free.
    """
    candidates: list[Path] = []
    if config_path:
        candidates.append(Path(config_path).resolve().parent / ".env")
    candidates.append(Path.cwd() / ".env")

    loaded: list[str] = []
    seen: set[Path] = set()
    for env_path in candidates:
        if env_path in seen or not env_path.is_file():
            continue
        seen.add(env_path)
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
        loaded.append(str(env_path))
    return loaded


def quiet_ml_noise() -> None:
    """Silence noisy ML-library output: torch's CUDA-driver UserWarning,
    HuggingFace/transformers progress bars, and semlix's sentence-transformers
    FutureWarning. Idempotent, and must run *before* the embedding model is
    imported (i.e. before build_backend constructs a provider)."""
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
    os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    warnings.filterwarnings("ignore", message=r".*CUDA initialization.*")
    warnings.filterwarnings("ignore", message=r".*get_sentence_embedding_dimension.*")
    warnings.filterwarnings("ignore", message=r".*resume_download.*")
