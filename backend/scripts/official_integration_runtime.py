"""Explicit isolated acceptance runtime; never the production Compose runtime."""
import asyncio
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
assert ROOT.parent.name == "RoamSync-official-integration-20261020"
sys.path.insert(0, str(ROOT))
from app.config import Settings, get_settings

source = Settings(_env_file="E:/Study/RoamSync/.env")
for name in ("planner_provider", "planner_base_url", "planner_model", "planner_timeout_seconds", "planner_max_output_tokens", "planner_reasoning_effort", "planner_api_key", "amap_rest_key", "tavily_api_key", "roamsync_tavily_api_key", "tavily_base_url", "tavily_proxy_url"):
    value = getattr(source, name)
    os.environ[name.upper()] = value.get_secret_value() if hasattr(value, "get_secret_value") else str(value)
# Windows host processes cannot use the Docker-only proxy alias. Process only.
os.environ["PLANNER_PROXY_URL"] = ""
os.environ["TAVILY_PROXY_URL"] = os.environ["TAVILY_PROXY_URL"].replace("host.docker.internal", "127.0.0.1")
os.environ.update(APP_ENV="test", ALLOW_MAP_ESTIMATES="false",
    DATABASE_URL="postgresql+psycopg://write_test:write_test_only@127.0.0.1:51420/roamsync_official_integration_live_test",
    LANGGRAPH_DATABASE_URL="postgresql://write_test:write_test_only@127.0.0.1:51420/roamsync_official_integration_live_test")
get_settings.cache_clear()
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "migrate":
        from alembic import command
        from alembic.config import Config
        config = Config(str(ROOT / "alembic.ini"))
        config.set_main_option("script_location", str(ROOT / "migrations"))
        command.upgrade(config, "head")
        async def checkpoints():
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
            async with AsyncPostgresSaver.from_conn_string(get_settings().checkpoint_database_url) as saver:
                await saver.setup()
        asyncio.run(checkpoints())
    elif mode == "api":
        import uvicorn
        server = uvicorn.Server(uvicorn.Config("app.main:app", host="127.0.0.1", port=18021, log_level="warning", access_log=False))
        asyncio.run(server.serve())
    elif mode == "worker":
        from app.agent_worker import main
        asyncio.run(main())
    else:
        raise ValueError("Only migrate/api/worker are supported")
