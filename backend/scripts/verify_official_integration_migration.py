"""Full-row preservation of synthetic legacy data around 0037; disposable DB only."""
import asyncio
from datetime import UTC, date, datetime, time
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
assert os.environ.get("APP_ENV") == "test"
assert os.environ.get("DATABASE_URL") == "postgresql+psycopg://write_test:write_test_only@127.0.0.1:51420/roamsync_arrangement_migration_test"
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

def migrate(target, direction="upgrade"):
    subprocess.run([sys.executable, "-m", "alembic", direction, target], cwd=ROOT, check=True)

migrate("20261018_0036")
from sqlalchemy import create_engine, select, text
from app.database import Activity, DayPlan, PlaceCandidate, SourceRecord, TripPreferences, session_factory
from app.repository import create_trip
from app.requirements import capture_explicit_requirements
from app.schemas import TripCreate

async def seed():
    async with session_factory() as s:
        t = await create_trip(s, TripCreate(title="synthetic legacy compatibility", destination="南京市", start_date=date(2026, 11, 7), end_date=date(2026, 11, 8)))
        days = list((await s.scalars(select(DayPlan).where(DayPlan.trip_id == t.id).order_by(DayPlan.position))).all())
        source = SourceRecord(trip_id=t.id, title="synthetic fixture", url="https://example.org/synthetic", provider="migration_fixture", queried_at=datetime.now(UTC), confidence="low")
        s.add(source); await s.flush()
        place = PlaceCandidate(trip_id=t.id, source_record_id=source.id, slug="legacy-fixed", name="synthetic fixed appointment", category="culture", neighborhood="synthetic", description="Synthetic migration test only", longitude=Decimal("118.8"), latitude=Decimal("32.0"), suggested_duration_minutes=90, estimated_cost_fen=0, rating=Decimal("3.0"), tags=[])
        s.add(place); await s.flush()
        s.add(Activity(day_plan_id=days[1].id, place_candidate_id=place.id, scheduled_time=time(14), duration_minutes=90, estimated_cost_fen=0, status="planned", position=0, schedule_locked=True, importance="must_do", can_skip=False, version=4))
        prefs = await s.get(TripPreferences, t.id)
        if prefs is None:
            prefs = TripPreferences(trip_id=t.id); s.add(prefs)
        prefs.free_text_requirements = "第二天慢游"
        prefs.requirement_records = capture_explicit_requirements([], "第二天慢游", scope={"kind": "trip", "trip_id": str(t.id), "city": "南京市"}, source_ref="synthetic-migration", force=True)
        assert prefs.requirement_records
        prefs.version = 3; t.version = 5
        await s.commit()

asyncio.run(seed())
engine = create_engine(os.environ["DATABASE_URL"])
def snapshot():
    with engine.connect() as c:
        return {table: {"rows": len(rows), "sha256": hashlib.sha256("\n".join(rows).encode()).hexdigest()}
            for table in ("trips", "day_plans", "trip_preferences", "source_records", "place_candidates", "activities")
            for rows in [[r[0] for r in c.execute(text(f'SELECT to_jsonb(t)::text FROM "{table}" t ORDER BY to_jsonb(t)::text'))]]}
before = snapshot(); steps = []
for target, direction in (("head", "upgrade"), ("20261018_0036", "downgrade"), ("head", "upgrade")):
    if direction == "downgrade":
        with engine.connect() as c:
            assert c.scalar(text("SELECT count(*) FROM trip_arrangement_items")) == 0
    migrate(target, direction)
    after = snapshot(); assert after == before, (target, after, before)
    steps.append({"target": target, "direction": direction, "legacy_rows_unchanged": True})
with engine.connect() as c:
    version = c.scalar(text("SELECT version_num FROM alembic_version"))
    assert version == "20261019_0037"
engine.dispose()
out = ROOT.parent / "docs/evidence/official-integration-20261020/migration-compatibility.json"
out.write_text(json.dumps({"result": "PASS", "legacy_tables": before, "steps": steps, "final_version": version, "scope": "synthetic legacy Trip, two days, locked Activity/version4 and Requirements/version3; empty new-table downgrade only; no production DB"}, indent=2)+"\n", encoding="utf-8")
print("PASS: six legacy table full-row hashes unchanged, including Activity/Requirements versions")
