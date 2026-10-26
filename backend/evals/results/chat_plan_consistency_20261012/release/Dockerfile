FROM roamsync-chat-runtime-base:20261012 AS production
COPY app/ /app/app/
CMD ["uv", "run", "--no-sync", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM production AS test
COPY --from=roamsync-chat-consistency-20261012-api-test /app/.venv /app/.venv
COPY tests/ /app/tests/
CMD ["sh", "-c", "uv run --no-sync alembic upgrade head && uv run --no-sync pytest tests/test_saved_plan_notes.py -q"]
