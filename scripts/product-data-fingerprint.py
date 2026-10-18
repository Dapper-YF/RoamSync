"""Read-only business row fingerprints; run inside the official API container.

No row contents or credentials are emitted. Ignore the newly defaulted empty
requirement_records column only when comparing the historical schema.
"""
import json
import os
import psycopg
from psycopg import sql

with psycopg.connect(os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")) as conn:
    names = conn.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename").fetchall()
    result = {}
    for (name,) in names:
        if name == "alembic_version" or name.startswith("checkpoint"):
            continue
        row = sql.SQL("(to_jsonb(t) - 'requirement_records')") if name == "trip_preferences" else sql.SQL("to_jsonb(t)")
        query = sql.SQL("SELECT count(*), md5(coalesce(string_agg(md5({row}::text), '' ORDER BY md5({row}::text)), '')) FROM {table} t").format(row=row, table=sql.Identifier(name))
        count, digest = conn.execute(query).fetchone()
        result[name] = {"count": count, "sha_source": "sorted row md5", "fingerprint": digest}
    print(json.dumps(result, sort_keys=True, indent=2))
