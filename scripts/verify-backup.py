"""Restore an existing dump to a new portless tmpfs Postgres, compare row hashes.

Reads the dump/expected JSON only. Never connects to an official database.
python scripts/verify-backup.py --dump PATH --expected PATH --output NEW_FILE
The dump and restored rows must stay outside Git; evidence contains aggregates.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time
import uuid


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dump", required=True, type=Path)
    parser.add_argument("--expected", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("evidence output must not already exist")
    dump = args.dump.resolve(strict=True)
    expected = json.loads(args.expected.read_text(encoding="utf-8-sig"))["tables"]
    name = "roamsync-restore-test-" + uuid.uuid4().hex[:12]
    report = {"dump_sha256": hashlib.sha256(dump.read_bytes()).hexdigest(), "container": name, "passed": False}

    def run(*command, **kwargs):
        return subprocess.check_output(command, stderr=subprocess.PIPE, **kwargs)

    created = False
    started = time.monotonic()
    try:
        run("docker", "run", "-d", "--name", name, "--network", "none", "--tmpfs", "/var/lib/postgresql/data", "-e", "POSTGRES_USER=roamsync_restore_test", "-e", "POSTGRES_PASSWORD=restore_test_only", "-e", "POSTGRES_DB=roamsync_restore_test", "postgres:17-alpine")
        created = True
        for _ in range(60):
            ready = subprocess.run(["docker", "exec", name, "pg_isready", "-h", "127.0.0.1", "-U", "roamsync_restore_test", "-d", "roamsync_restore_test"], capture_output=True)
            if ready.returncode == 0:
                break
            time.sleep(1)
        else:
            raise RuntimeError("isolated restore database did not become ready")
        run("docker", "cp", str(dump), name + ":/tmp/backup.dump")
        run("docker", "exec", name, "pg_restore", "--exit-on-error", "--no-owner", "--no-privileges", "-U", "roamsync_restore_test", "-d", "roamsync_restore_test", "/tmp/backup.dump")
        sql = """SELECT format('SELECT json_build_object(''table'', %L, ''count'', count(*), ''sha'', md5(coalesce(string_agg(row_to_json(t)::text,E''\\n'' order by row_to_json(t)::text),''''))) FROM public.%I t', tablename, tablename) FROM pg_tables WHERE schemaname='public' ORDER BY tablename
\gexec
"""
        raw = run("docker", "exec", "-i", name, "psql", "-X", "-t", "-A", "-v", "ON_ERROR_STOP=1", "-U", "roamsync_restore_test", "-d", "roamsync_restore_test", "-f", "-", input=sql.encode())
        tables = {}
        for line in raw.decode().splitlines():
            row = json.loads(line)
            tables[row.pop("table")] = row
        report["tables"] = tables
        report["mismatches"] = sorted(table for table in set(expected) | set(tables) if expected.get(table) != tables.get(table))
        report["passed"] = not report["mismatches"]
    except (subprocess.CalledProcessError, RuntimeError, ValueError, KeyError) as exc:
        # pg_restore errors can contain row data; keep them out of portable evidence.
        report["error_type"] = type(exc).__name__
    finally:
        if created:
            cleanup = subprocess.run(["docker", "rm", "-f", name], capture_output=True)
            report["cleanup_passed"] = cleanup.returncode == 0
            report["passed"] &= report["cleanup_passed"]
        report["seconds"] = round(time.monotonic() - started, 3)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2))
    print(json.dumps({key: report[key] for key in ("passed", "seconds")}, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
