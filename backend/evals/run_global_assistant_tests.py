"""Reproduce the C targeted suite against an explicitly disposable database."""
import argparse
import asyncio
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

parser = argparse.ArgumentParser()
parser.add_argument("--database-url", required=True)
parser.add_argument("--b-app-path", help="Only for separate B/C workspace integration")
parser.add_argument("--junitxml", default="../docs/evidence/v2-ai/targeted-tests.xml")
args = parser.parse_args()
url = urlsplit(args.database_url)
if "test" not in url.path.lower() or url.hostname not in {"127.0.0.1", "localhost", "postgres-test"}:
    parser.error("Use an explicitly named test database on localhost or postgres-test")
os.environ.update(DATABASE_URL=args.database_url, APP_ENV="test", ALLOW_MAP_ESTIMATES="true",
    LANGGRAPH_DATABASE_URL=args.database_url.replace("postgresql+psycopg://", "postgresql://"),
    PLANNER_API_KEY="", PLANNER_MODEL="")
os.chdir(Path(__file__).resolve().parents[1])
sys.path.insert(0, str(Path.cwd()))
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
import app
if args.b_app_path:
    sys.dont_write_bytecode = True
    app.__path__.append(args.b_app_path)
import pytest
tests = ["global_assistant", "assistant_place_adapter", "assistant_answers", "assistant_tools", "assistant_stream",
    "assistant_stream_api", "companion_runtime", "companion_conversation_policy", "companion_knowledge",
    "companion_knowledge_strategy", "companion_fact_safety", "companion_facts", "companion_answer_reliability", "travel_goal_routing"]
raise SystemExit(pytest.main([*(f"tests/test_{name}.py" for name in tests), "--tb=short", f"--junitxml={args.junitxml}"]))
