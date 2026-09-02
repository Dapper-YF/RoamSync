FROM ghcr.io/astral-sh/uv:0.11.15 AS uv

FROM python:3.11-slim AS base
COPY --from=uv /uv /uvx /bin/
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"
COPY pyproject.toml uv.lock ./
COPY alembic.ini ./
COPY migrations ./migrations
COPY app ./app

FROM base AS production
RUN uv sync --frozen --no-dev
CMD ["sh", "-c", "uv run --no-sync alembic upgrade head && uv run --no-sync uvicorn app.main:app --host 0.0.0.0 --port 8000"]

FROM base AS test
COPY tests ./tests
RUN uv sync --frozen

