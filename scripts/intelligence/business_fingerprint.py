"""Read-only business-table change detection, never emits rows or credentials."""
import json
import os
import psycopg
from psycopg import sql

with psycopg.connect(os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")) as connection:
    names = connection.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename").fetchall()
    result = {}
    for (name,) in names:
        if name == "alembic_version" or name.startswith("checkpoint"):
            continue
        query = sql.SQL("SELECT count(*), md5(coalesce(string_agg(md5(to_jsonb(t)::text), '' ORDER BY md5(to_jsonb(t)::text)), '')) FROM {table} t").format(table=sql.Identifier(name))
        count, fingerprint = connection.execute(query).fetchone()
        result[name] = {"count": count, "fingerprint": fingerprint}
    print(json.dumps(result, sort_keys=True, indent=2))
