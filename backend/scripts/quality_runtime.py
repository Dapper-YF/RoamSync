"""Canonical-source isolated runtime; uses actual configured providers, never production DB."""
import asyncio
import os
import sys
import assistant_p0_eval as base

# Match the production planner instead of the Settings class's test defaults.
for name in ("planner_reasoning_effort","planner_max_candidates","planner_timeout_seconds","planner_max_output_tokens"):
    os.environ[name.upper()]=str(getattr(base.source,name))
base.get_settings.cache_clear()

if __name__=="__main__":
    mode=sys.argv[1]
    if mode=="init":
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        async def init():
            async with AsyncPostgresSaver.from_conn_string(base.get_settings().checkpoint_database_url) as saver:
                await saver.setup()
        asyncio.run(init())
    elif mode=="api":
        import uvicorn
        asyncio.run(uvicorn.Server(uvicorn.Config("app.main:app",host="127.0.0.1",port=18024,log_level="warning")).serve())
    elif mode=="worker":
        from app.agent_worker import main
        asyncio.run(main())
