"""B-owned tables on separate metadata. D owns migration and main DB binding.

Never call create_all on a production engine. Tests/dev explicitly initialize
these tables. Both PostgreSQL and SQLite use atomic ON CONFLICT upserts.
"""
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Column, DateTime, ForeignKey, Index, JSON, MetaData, String, Table, delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import Engine

from .contracts import Favorite, Place
from .images import project_images

metadata = MetaData()
places = Table("v2_content_places", metadata,
    Column("place_id", String(36), primary_key=True),
    Column("provider", String(30), nullable=False),
    Column("namespace", String(30), nullable=False),
    Column("provider_place_id", String(100), nullable=False),
    Column("snapshot", JSON, nullable=False),
)
Index("uq_v2_content_external_identity", places.c.provider, places.c.namespace, places.c.provider_place_id, unique=True)
favorites = Table("v2_content_favorites", metadata,
    Column("owner_id", String(200), primary_key=True),
    Column("place_id", String(36), ForeignKey(places.c.place_id), primary_key=True),
    Column("saved_at", DateTime(timezone=True), nullable=False),
)
Index("ix_v2_content_favorites_owner_saved", favorites.c.owner_id, favorites.c.saved_at)


class ContentRepository:
    def __init__(self, engine: Engine):
        self.engine = engine
        self.insert = {"sqlite": sqlite_insert, "postgresql": pg_insert}[engine.dialect.name]

    def save(self, place: Place) -> None:
        ref = place.ref.external_ref
        stmt = self.insert(places).values(place_id=str(place.ref.place_id), provider=ref.provider,
            namespace=ref.namespace, provider_place_id=ref.provider_place_id, snapshot=place.model_dump(mode="json"))
        stmt = stmt.on_conflict_do_update(index_elements=[places.c.place_id], set_={"snapshot": stmt.excluded.snapshot})
        with self.engine.begin() as conn:
            conn.execute(stmt)

    def get(self, place_id: UUID) -> Place | None:
        with self.engine.connect() as conn:
            value = conn.execute(select(places.c.snapshot).where(places.c.place_id == str(place_id))).scalar_one_or_none()
        return project_images(Place.model_validate(value)) if value else None

    def favorite(self, owner: str, place_id: UUID) -> None:
        with self.engine.begin() as conn:
            conn.execute(self.insert(favorites).values(owner_id=owner, place_id=str(place_id), saved_at=datetime.now(UTC))
                .on_conflict_do_nothing(index_elements=[favorites.c.owner_id, favorites.c.place_id]))

    def unfavorite(self, owner: str, place_id: UUID) -> None:
        with self.engine.begin() as conn:
            conn.execute(delete(favorites).where(favorites.c.owner_id == owner, favorites.c.place_id == str(place_id)))

    def is_favorite(self, owner: str, place_id: UUID) -> bool:
        with self.engine.connect() as conn:
            return conn.execute(select(favorites.c.place_id).where(favorites.c.owner_id == owner, favorites.c.place_id == str(place_id))).first() is not None

    def list_favorites(self, owner: str, limit: int = 50, offset: int = 0) -> list[Favorite]:
        with self.engine.connect() as conn:
            rows = conn.execute(select(places.c.snapshot, favorites.c.saved_at).join(favorites)
                .where(favorites.c.owner_id == owner).order_by(favorites.c.saved_at.desc(), favorites.c.place_id)
                .limit(limit).offset(offset)).all()
        return [Favorite(place=project_images(Place.model_validate(row.snapshot)), saved_at=row.saved_at.replace(tzinfo=UTC) if row.saved_at.tzinfo is None else row.saved_at) for row in rows]
