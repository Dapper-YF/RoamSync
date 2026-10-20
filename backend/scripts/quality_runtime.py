"""Isolated evidence-assistant acceptance only; never uses the official DB."""
import asyncio
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
assert ROOT.parent.name == "RoamSync-conversation-quality-20261020"
sys.path.insert(0, str(ROOT))
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
from app.config import Settings, get_settings
source = Settings(_env_file="E:/Study/RoamSync/.env")
for name in ("planner_provider", "planner_base_url", "planner_model", "planner_timeout_seconds", "planner_max_output_tokens", "planner_api_key", "amap_rest_key", "tavily_api_key", "roamsync_tavily_api_key", "tavily_base_url", "tavily_proxy_url"):
    value = getattr(source, name)
    os.environ[name.upper()] = value.get_secret_value() if hasattr(value, "get_secret_value") else str(value)
os.environ["PLANNER_PROXY_URL"] = ""
os.environ["TAVILY_PROXY_URL"] = os.environ["TAVILY_PROXY_URL"].replace("host.docker.internal", "127.0.0.1")
test_db = "roamsync_test_write_protection" if "test-db" in sys.argv else "roamsync_quality_live_test"
os.environ.update(APP_ENV="test", ALLOW_MAP_ESTIMATES="false",
    ROAMSYNC_ISOLATED_INTEGRATION="1", ROAMSYNC_INTEGRATION_TOKEN="evidence-local-test-only",
    ROAMSYNC_INTEGRATION_OWNER="evidence-local-test-user", ROAMSYNC_LOCAL_ORIGINS="http://127.0.0.1:3023",
    DATABASE_URL=f"postgresql+psycopg://write_test:write_test_only@127.0.0.1:51422/{test_db}",
    LANGGRAPH_DATABASE_URL=f"postgresql://write_test:write_test_only@127.0.0.1:51422/{test_db}")
get_settings.cache_clear()
if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "migrate":
        from alembic import command
        from alembic.config import Config
        cfg = Config(str(ROOT / "alembic.ini")); cfg.set_main_option("script_location", str(ROOT / "migrations"))
        command.upgrade(cfg, "head")
        async def checkpoints():
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
            async with AsyncPostgresSaver.from_conn_string(get_settings().checkpoint_database_url) as saver:
                await saver.setup()
        asyncio.run(checkpoints())
    elif mode == "api":
        import uvicorn
        asyncio.run(uvicorn.Server(uvicorn.Config("app.main:app", host="127.0.0.1", port=18023, log_level="warning", access_log=False)).serve())
    elif mode == "worker":
        from app.agent_worker import main
        asyncio.run(main())
