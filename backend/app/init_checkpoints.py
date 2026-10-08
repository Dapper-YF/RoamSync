import asyncio
import sys

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from app.config import get_settings


async def main() -> None:
    settings = get_settings()
    async with AsyncPostgresSaver.from_conn_string(
        settings.checkpoint_database_url
    ) as checkpointer:
        await checkpointer.setup()
    print("LangGraph checkpoint tables are ready")


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop)
    else:
        asyncio.run(main())
