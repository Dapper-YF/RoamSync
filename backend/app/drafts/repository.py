from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import JSON, Column, Integer, MetaData, String, Table, select, update

from .contracts import Draft, DraftCreate, DraftRun, RunRequest
from app.requirements import capture_explicit_requirements, valid_records

metadata = MetaData()
drafts = Table("v2_travel_drafts", metadata,
    Column("id", String(36), primary_key=True), Column("owner_id", String(200), nullable=False, index=True),
    Column("version", Integer, nullable=False), Column("snapshot", JSON, nullable=False))


class DraftError(Exception):
    def __init__(self, code, status=409):
        self.code, self.status = code, status


class DraftRepository:
    """D owns schema initialization. All mutations use a transaction + optimistic CAS."""
    def __init__(self, engine):
        self.engine = engine

    def create(self, owner: str, data: DraftCreate):
        draft = Draft(id=uuid4(), **data.model_dump(), version=1, status="active", saved=False,
                      plan=None, runs=[], updated_at=datetime.now(UTC))
        draft.requirement_records = capture_explicit_requirements([], data.requirements,
            scope={"kind": "draft", "draft_id": str(draft.id), "city": draft.city},
            source_ref=f"draft:{draft.id}:create", force=True)
        with self.engine.begin() as conn:
            conn.execute(drafts.insert().values(id=str(draft.id), owner_id=owner, version=1, snapshot=draft.model_dump(mode="json")))
        return draft

    def get(self, owner: str, draft_id: UUID, conn=None):
        if conn is None:
            with self.engine.connect() as connection:
                return self.get(owner, draft_id, connection)
        row = conn.execute(select(drafts.c.snapshot).where(drafts.c.id == str(draft_id), drafts.c.owner_id == owner)).first()
        if row is None:
            raise DraftError("draft_not_found", 404)
        return Draft.model_validate(row[0])

    def list(self, owner):
        with self.engine.connect() as conn:
            rows = conn.execute(select(drafts.c.snapshot).where(drafts.c.owner_id == owner)).all()
        return sorted([Draft.model_validate(row[0]) for row in rows], key=lambda d: d.updated_at, reverse=True)

    def mutate(self, owner, draft_id, version, fn):
        with self.engine.begin() as conn:
            draft = self.get(owner, draft_id, conn)
            if draft.version != version:
                raise DraftError("draft_version_conflict")
            fn(draft)
            draft.version += 1
            draft.updated_at = datetime.now(UTC)
            result = conn.execute(update(drafts).where(drafts.c.id == str(draft_id), drafts.c.owner_id == owner,
                drafts.c.version == version).values(version=draft.version, snapshot=draft.model_dump(mode="json")))
            if result.rowcount != 1:
                raise DraftError("draft_version_conflict")
            return draft

    def begin_run(self, owner, draft_id, request: RunRequest, source):
        self.recover_interrupted(owner=owner, draft_id=draft_id)
        current = self.get(owner, draft_id)
        for run in current.runs:
            if run.request_id == request.request_id:
                if (run.requirements != request.requirements
                        or sorted(run.target_day_indices) != request.target_day_indices):
                    raise DraftError("idempotency_key_reused")
                return current, run, False
        run = DraftRun(id=uuid4(), request_id=request.request_id, status="running", requirements=request.requirements,
                       target_day_indices=request.target_day_indices,
                       source=source, created_at=datetime.now(UTC), lease_expires_at=datetime.now(UTC) + timedelta(minutes=5))
        def start(draft):
            if draft.schema_version != 1:
                raise DraftError("candidate_protocol_required")
            if draft.status != "active":
                raise DraftError("draft_cancelled")
            if any(r.status == "running" for r in draft.runs):
                raise DraftError("draft_run_in_progress")
            if request.target_day_indices:
                if not draft.plan:
                    raise DraftError("draft_scope_requires_plan", 422)
                if any(day > draft.day_count for day in request.target_day_indices):
                    raise DraftError("draft_scope_out_of_range", 422)
            draft.runs.append(run)
        return self.mutate(owner, draft_id, request.expected_version, start), run, True

    def recover_interrupted(self, *, owner=None, draft_id=None, now=None):
        """Explicit startup/read recovery. CAS fences late model responses; no task platform.

        Legacy running rows have a five-minute deadline from created_at. A live
        request is bounded to 180 seconds, below the lease. Users can cancel at any time.
        """
        now = now or datetime.now(UTC)
        query = select(drafts)
        if owner is not None:
            query = query.where(drafts.c.owner_id == owner)
        if draft_id is not None:
            query = query.where(drafts.c.id == str(draft_id))
        with self.engine.connect() as conn:
            rows = conn.execute(query).mappings().all()
        recovered = 0
        for row in rows:
            draft = Draft.model_validate(row["snapshot"])
            if not any(r.status == "running" and (r.lease_expires_at or r.created_at + timedelta(minutes=5)) <= now for r in draft.runs):
                continue
            def interrupt(current):
                for run in current.runs:
                    if run.status == "running" and (run.lease_expires_at or run.created_at + timedelta(minutes=5)) <= now:
                        run.status, run.finished_at = "interrupted", now
                        run.error = "生成进程中断或租约过期，原草稿已保留。请重新生成。"
            try:
                self.mutate(row["owner_id"], draft.id, draft.version, interrupt)
                recovered += 1
            except DraftError:
                pass  # Another request already finished/cancelled/recovered this version.
        return recovered
