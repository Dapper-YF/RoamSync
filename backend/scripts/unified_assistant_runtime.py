"""Isolated runtime only. Load provider configuration in memory, never print secrets."""
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
assert ROOT.parent.name == "RoamSync-unified-assistant-20261020"
assert os.environ.get("ROAMSYNC_TASK_PG_PORT", "").isdigit()
from app.config import Settings

source = Settings(_env_file="E:/Study/RoamSync/.env")
for name in ("planner_provider", "planner_base_url", "planner_proxy_url", "planner_model", "planner_timeout_seconds", "planner_max_output_tokens", "planner_reasoning_effort", "planner_api_key", "amap_rest_key", "tavily_api_key", "roamsync_tavily_api_key", "tavily_base_url", "tavily_proxy_url"):
    value = getattr(source, name)
    os.environ[name.upper()] = value.get_secret_value() if hasattr(value, "get_secret_value") else str(value)
if os.environ.get("ROAMSYNC_TASK_DIRECT_MODEL") == "1":
    os.environ["PLANNER_PROXY_URL"] = ""  # Isolated per-process transport override.
if os.environ.get("ROAMSYNC_TASK_LOCAL_SEARCH_PROXY") == "1":
    # Canonical Compose uses the Docker host alias; this process runs on Windows.
    os.environ["TAVILY_PROXY_URL"] = os.environ["TAVILY_PROXY_URL"].replace("host.docker.internal", "127.0.0.1")
port = os.environ["ROAMSYNC_TASK_PG_PORT"]
os.environ.update(APP_ENV="test", DATABASE_URL=f"postgresql+psycopg://write_test:write_test_only@127.0.0.1:{port}/roamsync_unified_live_test",
    LANGGRAPH_DATABASE_URL=f"postgresql://write_test:write_test_only@127.0.0.1:{port}/roamsync_unified_live_test",
    ALLOW_MAP_ESTIMATES="false")
from app.config import get_settings
get_settings.cache_clear()

if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "migrate":
        from alembic.config import Config
        from alembic import command
        config = Config(str(ROOT / "alembic.ini"))
        config.set_main_option("script_location", str(ROOT / "migrations"))
        command.upgrade(config, "head")
        import asyncio
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        async def setup_checkpoints():
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
            async with AsyncPostgresSaver.from_conn_string(get_settings().checkpoint_database_url) as saver:
                await saver.setup()
        asyncio.run(setup_checkpoints())
    elif mode == "api":
        import asyncio, uvicorn
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        server = uvicorn.Server(uvicorn.Config("app.main:app", host="127.0.0.1", port=18020, log_level="warning", access_log=False))
        asyncio.run(server.serve())
    elif mode == "worker":
        import asyncio
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        from app.agent_worker import main
        asyncio.run(main())
