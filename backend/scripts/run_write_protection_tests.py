"""Run only with an explicitly named isolated test database."""
import asyncio
import os
from pathlib import Path
import sys

assert os.environ.get("APP_ENV") == "test"
assert os.environ.get("DATABASE_URL", "").endswith("/roamsync_test_write_protection")
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pytest
raise SystemExit(pytest.main(sys.argv[1:]))
