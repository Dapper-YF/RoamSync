"""Replay 0036 -> 0037 -> 0036 -> 0037 in a disposable named database."""
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import date

assert os.environ.get("APP_ENV") == "test"
assert "@127.0.0.1:" in os.environ.get("DATABASE_URL", "")
assert os.environ["DATABASE_URL"].endswith("/roamsync_arrangement_migration_test")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def migrate(*args):
    subprocess.run([sys.executable, "-m", "alembic", *args], cwd=ROOT, check=True)


migrate("upgrade", "20261018_0036")
from app.database import session_factory, Trip
from app.repository import create_trip
from app.schemas import TripCreate
from sqlalchemy import create_engine, text


async def legacy():
    async with session_factory() as s:
        row = await create_trip(s, TripCreate(title="synthetic legacy migration", destination="南京市", start_date=date(2026, 11, 7), end_date=date(2026, 11, 8)))
        return row.id


key = asyncio.run(legacy())
engine = create_engine(os.environ["DATABASE_URL"])
def count():
    with engine.connect() as c:
        return {"trip": c.scalar(text("SELECT count(*) FROM trips WHERE id=:id AND version=1"), {"id": key}),
                "days": c.scalar(text("SELECT count(*) FROM day_plans WHERE trip_id=:id"), {"id": key})}

before = count()
migrate("upgrade", "head")
after = count()
with engine.connect() as c:
    assert c.scalar(text("SELECT count(*) FROM trip_arrangement_items")) == 0
assert before == after == {"trip": 1, "days": 2}
migrate("downgrade", "20261018_0036")
assert count() == before
migrate("upgrade", "head")
assert count() == before
engine.dispose()
out = ROOT.parent / "docs/evidence/natural-assistant/migration.json"
out.write_text(json.dumps({"database": "roamsync_arrangement_migration_test", "sequence": ["0036", "0037", "0036", "0037"],
    "before": before, "after_each_step": after, "result": "PASS", "scope": "synthetic isolated database only; no populated arrangement downgrade"}, indent=2), encoding="utf-8")
print("PASS: legacy Trip/day data survived upgrade, empty-table downgrade and re-upgrade")
