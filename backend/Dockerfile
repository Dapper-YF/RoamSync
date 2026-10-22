FROM ghcr.io/astral-sh/uv:0.11.15 AS uv

FROM python:3.11-slim AS base
COPY --from=uv /uv /uvx /bin/
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"
COPY pyproject.toml uv.lock ./

FROM base AS production
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev
COPY alembic.ini ./
COPY migrations ./migrations
COPY app ./app
COPY evals ./evals
COPY Dockerfile .dockerignore ./
COPY scripts/write_build_manifest.py ./scripts/write_build_manifest.py
RUN python scripts/write_build_manifest.py
CMD ["sh", "-c", "uv run --no-sync alembic upgrade head && uv run --no-sync uvicorn app.main:app --host 0.0.0.0 --port 8000"]

FROM base AS test
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen
COPY alembic.ini ./
COPY migrations ./migrations
COPY app ./app
COPY evals ./evals
COPY tests ./tests
