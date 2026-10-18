"""Explicit isolated development runner; never imports main or seeds Trips.

Set ROAMSYNC_CONTENT_DATABASE_URL=sqlite:///... and initialize with
`python -m app.place_content.dev_app --init-db`, then run
`uvicorn app.place_content.dev_app:create_app --factory --port 8011`.
Production table migrations and router/owner integration belong to line D.
"""
import hmac
import os

from fastapi import FastAPI, Header, HTTPException
from sqlalchemy import create_engine

from app.config import get_settings
from .provider import AMapContentProvider
from .repository import ContentRepository, metadata
from .routes import create_router
from .service import PlaceContentService


def dev_engine():
    url = os.environ.get("ROAMSYNC_CONTENT_DATABASE_URL", "")
    if not url.startswith("sqlite:///"):
        raise RuntimeError("Standalone runner requires explicit isolated sqlite:/// database; D owns production integration")
    return create_engine(url, connect_args={"check_same_thread": False})


def create_app() -> FastAPI:
    engine = dev_engine()
    token = os.environ.get("ROAMSYNC_CONTENT_ACCESS_TOKEN", "")
    owner = os.environ.get("ROAMSYNC_CONTENT_OWNER_ID", "")

    def trusted_owner(authorization: str | None = Header(default=None)) -> str:
        if not token or not owner:
            raise HTTPException(503, detail={"code": "owner_boundary_not_configured"})
        if not authorization or not hmac.compare_digest(authorization, f"Bearer {token}"):
            raise HTTPException(401, detail={"code": "unauthorized"})
        return owner

    app = FastAPI(title="RoamSync B content slice (isolated development)")
    app.include_router(create_router(PlaceContentService(AMapContentProvider(get_settings().amap_rest_key), ContentRepository(engine)), trusted_owner))
    return app


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--init-db", action="store_true", required=True)
    parser.parse_args()
    engine = dev_engine()
    metadata.create_all(engine)
    print("Isolated content tables initialized; no Trip or production tables accessed")
