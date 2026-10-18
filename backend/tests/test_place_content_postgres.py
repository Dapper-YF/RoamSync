"""Real SQL adapter check; run only inside an explicitly named test database."""
import os
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

from app.place_content.provider import normalize_poi
from app.place_content.repository import ContentRepository, metadata


def test_postgres_concurrent_favorite_identity_and_owner_isolation():
    url = os.environ.get("DATABASE_URL", "")
    if os.environ.get("APP_ENV") != "test" or not url or make_url(url).database != "roamsync_test":
        pytest.skip("requires isolated roamsync_test PostgreSQL and APP_ENV=test")
    engine = create_engine(url)
    metadata.create_all(engine)
    repo = ContentRepository(engine)
    place = normalize_poi({"id": "BTESTCONCURRENT", "name": "合成地点", "location": "120,30", "typecode": "110000"})
    repo.save(place)
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda _: repo.favorite("content-synthetic-alice", place.ref.place_id), range(24)))
    assert len(repo.list_favorites("content-synthetic-alice")) == 1
    assert repo.list_favorites("content-synthetic-bob") == []
    repo.unfavorite("content-synthetic-alice", place.ref.place_id)
    repo.unfavorite("content-synthetic-alice", place.ref.place_id)
    assert repo.list_favorites("content-synthetic-alice") == []
    engine.dispose()
