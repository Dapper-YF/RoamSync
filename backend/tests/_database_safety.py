"""Validate test destinations before any application module/engine is imported."""
import re
from collections.abc import Mapping

from sqlalchemy.engine import make_url


def allows_fixture_database(value: str, *legacy_names: str) -> bool:
    """Allow named fixtures or a unique Stage6 test DB after the global guard."""
    try:
        url = make_url(value)
        name = url.database or ""
        return bool(url.get_backend_name() == "postgresql" and url.host and not url.query
            and (name in legacy_names or re.fullmatch(r"roamsync_s6_[a-z0-9_]+_test", name)))
    except Exception:
        return False


def validate_test_databases(environ: Mapping[str, str]) -> None:
    if environ.get("APP_ENV") != "test":
        raise ValueError("APP_ENV=test must be explicitly set before collecting tests")
    if environ.get("ROAMSYNC_LOCAL_PRODUCT") == "1":
        raise ValueError("official local-product mode cannot be used by pytest")
    if not environ.get("DATABASE_URL"):
        raise ValueError("DATABASE_URL must explicitly name an isolated test database")
    identities = {}
    for name in ("DATABASE_URL", "LANGGRAPH_DATABASE_URL", "PROMOTION_TEST_DATABASE_URL"):
        value = environ.get(name)
        if not value:
            continue
        try:
            url = make_url(value)
            valid = (
                url.get_backend_name() == "postgresql"
                and url.host
                and url.username
                and re.fullmatch(r"[a-z0-9_]+", url.database or "")
                and re.search(r"(?:^|_)test(?:_|$)", url.database or "")
                and not url.query
            )
            identity = (url.host.casefold() if url.host else "", url.port or 5432, url.database)
        except Exception:
            valid = False
        if not valid:
            # Never include the URL, driver exception, credentials or query in errors.
            raise ValueError(f"{name} must use PostgreSQL and a database with a separate 'test' name token; URL query overrides are forbidden")
        identities[name] = identity
    checkpoint = identities.get("LANGGRAPH_DATABASE_URL")
    if checkpoint and checkpoint != identities["DATABASE_URL"]:
        raise ValueError("LANGGRAPH_DATABASE_URL must target the same isolated database as DATABASE_URL")


def configure_test_databases(environ):
    validate_test_databases(environ)
    # Settings also reads .env. Pin the fallback BEFORE app.config is imported,
    # otherwise an unexported checkpoint URL in a local .env could still win.
    if not environ.get("LANGGRAPH_DATABASE_URL"):
        environ["LANGGRAPH_DATABASE_URL"] = make_url(environ["DATABASE_URL"]).set(drivername="postgresql").render_as_string(hide_password=False)


if __name__ == "__main__":
    import os
    try:
        configure_test_databases(os.environ)
    except ValueError as exc:
        raise SystemExit(f"RoamSync test database safety: {exc}") from None
