"""Environment setup shared by the CLI/MCP entrypoints."""
from __future__ import annotations

import os
import warnings


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
