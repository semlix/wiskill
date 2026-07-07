# wiskill — hybrid (lexical + semantic) wiki service.
# The all-MiniLM embedding model is baked in so startup needs no network.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/opt/hf-cache \
    TRANSFORMERS_VERBOSITY=error \
    HF_HUB_DISABLE_PROGRESS_BARS=1 \
    TOKENIZERS_PARALLELISM=false

# uv for fast installs.
RUN pip install --no-cache-dir uv

WORKDIR /app

# Install dependencies first (better layer caching): copy metadata, then source.
COPY pyproject.toml README.md ./
COPY wiskill ./wiskill
RUN uv pip install --system -e ".[semantic,mcp]"

# Bake the default embedding model into the image's HF cache.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# Non-root; the HF cache must be readable by the runtime user.
RUN useradd --create-home --uid 10001 app && chown -R app:app /opt/hf-cache /app
USER app

EXPOSE 8000

# Config is mounted at /app/wiskill.toml; data at /app/data.
ENTRYPOINT ["wiskill", "--config", "/app/wiskill.toml", "serve", "--with-mcp", "--host", "0.0.0.0", "--port", "8000"]
