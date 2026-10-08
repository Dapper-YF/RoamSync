"""CLI entry point for the independent Goal-Aware Planning demo fixture."""
import argparse
import asyncio

from app.database import session_factory
from app.demo_seed import GOAL_AWARE_DEMO_TRIP_ID, seed_goal_aware_demo_data


async def run(reset: bool) -> None:
    async with session_factory() as session:
        changed = await seed_goal_aware_demo_data(session, reset=reset)
    action = "reset" if reset else "seeded" if changed else "already exists"
    print(f"Goal-aware demo trip {GOAL_AWARE_DEMO_TRIP_ID}: {action}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Create the independent Goal-Aware demo trip.")
    parser.add_argument("--reset", action="store_true", help="Replace only the Goal-Aware demo trip.")
    args = parser.parse_args()
    asyncio.run(run(args.reset))


if __name__ == "__main__":
    main()
