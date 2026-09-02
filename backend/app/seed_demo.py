import argparse
import asyncio

from app.database import session_factory
from app.demo_seed import DEMO_TRIP_ID, seed_demo_data


async def run(reset: bool) -> None:
    async with session_factory() as session:
        changed = await seed_demo_data(session, reset=reset)
    action = "reset" if reset else "seeded" if changed else "already exists"
    print(f"Demo trip {DEMO_TRIP_ID}: {action}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Create the fixed RoamSync demo trip.")
    parser.add_argument("--reset", action="store_true", help="Replace only the fixed demo trip.")
    args = parser.parse_args()
    asyncio.run(run(args.reset))


if __name__ == "__main__":
    main()
