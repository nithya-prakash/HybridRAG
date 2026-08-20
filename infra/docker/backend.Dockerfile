# syntax=docker/dockerfile:1

FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.5.4 /uv /uvx /bin/

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

COPY backend/pyproject.toml backend/uv.lock* ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-install-project --no-dev

# tiktoken downloads its BPE encoding file over HTTPS on first use unless cached.
# Baking it into the image at build time means the worker never has a runtime
# network dependency just to count tokens.
ENV TIKTOKEN_CACHE_DIR=/app/.tiktoken_cache
RUN .venv/bin/python -c "import tiktoken; tiktoken.get_encoding('cl100k_base')"

# Same reasoning for the cross-encoder reranker model: downloads from
# Hugging Face on first use unless cached, so bake it in at build time.
ENV HF_HOME=/app/.hf_cache HF_HUB_DISABLE_TELEMETRY=1
RUN .venv/bin/python -c "from sentence_transformers import CrossEncoder; CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')"

# And for the local embedding model — this is what makes EMBEDDING_PROVIDER=local
# (the default; see app/core/config.py) work with zero external API key and
# no runtime network dependency once the image is built.
RUN .venv/bin/python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-en-v1.5')"

COPY backend/app ./app
# alembic.ini + alembic/ weren't copied here until Phase 9's production
# compose surfaced the gap: `alembic upgrade head` had only ever been run
# from a host checkout (CI, local `uv run`) — a deployed container had no
# way to migrate itself at all. Confirmed by hitting exactly that failure
# ("No 'script_location' key found in configuration") when the Phase 9
# one-shot `migrate` service first tried to run inside this image.
COPY backend/alembic.ini ./alembic.ini
COPY backend/alembic ./alembic
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev

FROM python:3.12-slim AS runtime

RUN groupadd --system app && useradd --system --gid app app

WORKDIR /app

COPY --from=builder /app /app
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    TIKTOKEN_CACHE_DIR=/app/.tiktoken_cache \
    HF_HOME=/app/.hf_cache \
    HF_HUB_OFFLINE=1

RUN mkdir -p /data/uploads && chown -R app:app /app /data

USER app

EXPOSE 8000

# The reranker's and the local embedding backend's warm_up() both run during
# FastAPI startup (before the app accepts connections) — loading two local
# models needs comfortable headroom in this window.
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
