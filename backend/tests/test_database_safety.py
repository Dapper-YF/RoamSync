import os
from pathlib import Path
import subprocess
import sys

import pytest

from _database_safety import allows_fixture_database, validate_test_databases


@pytest.mark.parametrize("database,allowed", [
    ("roamsync_test_write_protection", True),
    ("roamsync_s6_official_full_20261026_test", True),
    ("roamsync_s6_official_promotion_20261026_test", True),
    ("roamsync", False), ("roamsync_s6_production", False),
    ("other_test", False), ("roamsync_s6_test_backup", False),
])
def test_fixture_database_gate_keeps_unique_test_namespace(database, allowed):
    assert allows_fixture_database(environment(database)["DATABASE_URL"], "roamsync_test_write_protection") is allowed


def test_fixture_database_gate_rejects_query_override_and_non_postgres():
    assert not allows_fixture_database(environment()["DATABASE_URL"] + "?dbname=roamsync", "roamsync_test")
    assert not allows_fixture_database("sqlite:///roamsync_s6_fixture_test")


def environment(database="roamsync_test"):
    return {"APP_ENV": "test", "DATABASE_URL": f"postgresql+psycopg://fixture:secret@postgres-test:5432/{database}"}


@pytest.mark.parametrize("database", ["roamsync_test", "roamsync_agent_b_test", "promotion_test", "roamsync_test_write_protection"])
def test_accepts_explicit_test_database_names(database):
    validate_test_databases(environment(database))


@pytest.mark.parametrize("changes", [
    {"APP_ENV": "development"}, {"APP_ENV": ""}, {"DATABASE_URL": ""},
    {"DATABASE_URL": environment("roamsync")["DATABASE_URL"]},
    {"DATABASE_URL": environment("latest")["DATABASE_URL"]},
    {"DATABASE_URL": "postgresql+psycopg://fixture:secret@postgres-test/roamsync_test?dbname=roamsync"},
    {"DATABASE_URL": "sqlite:///roamsync_test"},
    {"LANGGRAPH_DATABASE_URL": environment("roamsync")["DATABASE_URL"]},
    {"LANGGRAPH_DATABASE_URL": environment("other_test")["DATABASE_URL"]},
    {"PROMOTION_TEST_DATABASE_URL": environment("roamsync")["DATABASE_URL"]},
    {"ROAMSYNC_LOCAL_PRODUCT": "1"},
])
def test_refuses_unsafe_destinations_without_disclosing_credentials(changes):
    with pytest.raises(ValueError) as error:
        validate_test_databases({**environment(), **changes})
    assert "secret" not in str(error.value)
    assert "postgresql://" not in str(error.value)


def test_application_is_not_imported_before_safety_failure(tmp_path):
    """Exercise the real pytest lifecycle; neither app import nor a DB is needed."""
    root = Path(__file__).parent
    for name in ("conftest.py", "_database_safety.py"):
        (tmp_path / name).write_bytes((root / name).read_bytes())
    (tmp_path / "test_probe.py").write_text("raise RuntimeError('APPLICATION_IMPORT_REACHED')\n")
    env = {**os.environ, **environment("roamsync")}
    result = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", str(tmp_path)],
                            cwd=tmp_path, env=env, capture_output=True, text=True, timeout=20)
    assert result.returncode == pytest.ExitCode.USAGE_ERROR
    output = result.stdout + result.stderr
    assert "RoamSync test database safety" in output
    assert "APPLICATION_IMPORT_REACHED" not in output
    assert "secret" not in output


def test_local_dotenv_cannot_redirect_checkpoint_database(tmp_path):
    root = Path(__file__).parent
    for name in ("conftest.py", "_database_safety.py"):
        (tmp_path / name).write_bytes((root / name).read_bytes())
    (tmp_path / ".env").write_text("LANGGRAPH_DATABASE_URL=postgresql://fixture:secret@production/roamsync\n")
    (tmp_path / "test_probe.py").write_text(
        "from pydantic_settings import BaseSettings, SettingsConfigDict\n"
        "class Settings(BaseSettings):\n"
        "    langgraph_database_url: str = ''\n"
        "    model_config = SettingsConfigDict(env_file='.env')\n"
        "def test_checkpoint():\n"
        "    assert Settings().langgraph_database_url.endswith('/roamsync_test')\n")
    env = {**os.environ, **environment()}
    env.pop("LANGGRAPH_DATABASE_URL", None)
    env.pop("PROMOTION_TEST_DATABASE_URL", None)
    env.pop("ROAMSYNC_LOCAL_PRODUCT", None)
    result = subprocess.run([sys.executable, "-m", "pytest", "-q", str(tmp_path)],
                            cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, "test initialization did not pin checkpoint destination"
