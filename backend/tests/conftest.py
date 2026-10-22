"""Fail closed before test collection imports app.database or app.main."""
import os

import pytest

from _database_safety import configure_test_databases


def pytest_configure(config):
    try:
        configure_test_databases(os.environ)
    except ValueError as exc:
        raise pytest.UsageError(f"RoamSync test database safety: {exc}") from None
