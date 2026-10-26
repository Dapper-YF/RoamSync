"""Read-only release fingerprint; run on stdin in the official API container."""
import hashlib
import json

import psycopg
from psycopg import sql

from app.config import get_settings


tables = ("trips", "day_plans", "activities", "plan_revisions", "planning_runs",
          "expenses", "assistant_sessions")
url = str(get_settings().database_url).replace("postgresql+psycopg://", "postgresql://")
with psycopg.connect(url, options="-c default_transaction_read_only=on") as connection:
    connection.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
    report = {"read_only": True, "tables": {}}
    for table in tables:
        digest = hashlib.sha256()
        count = 0
        with connection.cursor() as cursor:
            cursor.execute(sql.SQL("SELECT row_to_json(t)::text FROM {} t ORDER BY id").format(sql.Identifier(table)))
            for (row,) in cursor:
                digest.update(row.encode("utf-8"))
                digest.update(b"\n")
                count += 1
        report["tables"][table] = {"count": count, "sha256": digest.hexdigest()}
    report["working_runs"] = connection.execute(
        "SELECT count(*) FROM planning_runs WHERE status IN ('queued','researching','planning','validating','running')").fetchone()[0]
    print(json.dumps(report))
