import uuid
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Header, Query, Response, status
from fastapi.responses import JSONResponse
from app.formal_write import FormalWriteConflictError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import engine, get_session, session_factory
from app.demo_seed import DEMO_TRIP_ID, seed_demo_data
from app.maps_service import (
    MapProviderError,
    recalculate_day_route,
    search_amap_cities,
    search_amap_location_pois,
    search_amap_places,
)
from app.planner_repository import (
    ActivityDecisionSemanticsError,
    ActivityNotFoundError,
    ActivityVersionConflictError,
    DayPlanNotFoundError,
    DuplicatePlaceError,
    InvalidActivityOrderError,
    InvalidActivityMoveError,
    PlaceCandidateNotFoundError,
    add_activity,
    delete_activity,
    get_candidates,
    get_day_plan,
    get_day_plans,
    get_planning_budget,
    reorder_activities,
    move_activity,
    update_activity,
)
from app.planning_context import build_planning_context
from app.planning_intent_service import (
    IntentContextError,
    UnsupportedPlanningIntentError,
    resolve_planning_intent,
)
from app.openai_intent_parser import build_semantic_intent_provider
from app.planning_graph_runtime import execute_planning_run
from app.planning_run_repository import (
    InvalidPlanningRunStateError,
    PlanRevisionNotFoundError,
    PlanningRunNotFoundError,
    StalePlanningRunError,
    RecoveryPlanningConflictError,
    create_planning_run,
    get_latest_revision,
    get_planning_run,
    list_planning_runs,
    reject_revision,
)
from app.trip_execution_service import (
    InvalidTripExecutionStateError,
    TripExecutionNotFoundError,
    apply_trip_execution_action,
    extend_stay,
    leave_early,
    request_dynamic_replan,
    get_trip_execution,
    start_trip_execution,
)
from app.experience_replanning_service import ensure_experience_recovery
from app.navigation.providers import RoutingProviderError, UnavailableRoutingProvider
from app.navigation.execution_read_model import get_execution_read_model
from app.navigation.session_service import (
    NavigationSessionConflictError,
    NavigationSessionNotFoundError,
    NavigationSessionStateError,
    StaleNavigationWriteError,
    apply_location_update,
    apply_navigation_session_action,
    create_navigation_session,
    get_navigation_session,
    navigation_session_response,
    refresh_route,
)
from app.navigation.observation_ingestion import (
    NavigationObservationConflictError,
    NavigationObservationNotFoundError,
    ingest_navigation_observation,
)
from app.navigation.start_navigation import NavigationStartConflictError, start_navigation
from app.plan_revision_service import InvalidPlanRevisionError, accept_plan_revision
from app.repository import (
    IdempotencyConflictError,
    TripDateConflictError,
    TripNotFoundError,
    TripVersionConflictError,
    TripPreferencesVersionConflictError,
    archive_trip,
    create_expense,
    create_trip,
    delete_trip,
    duplicate_trip,
    get_budget,
    get_trip,
    get_trip_deletion_preview,
    get_trip_preferences,
    list_trips,
    update_trip,
    update_trip_preferences,
)
from app.schemas import (
    BudgetResponse,
    CitySuggestionResponse,
    ActivityCreate,
    ActivityOrderUpdate,
    ActivityResponse,
    ActivityUpdate,
    ActivityMoveRequest,
    ActivityMoveResponse,
    DayPlanResponse,
    DemoResetResponse,
    DynamicReplanResponse,
    ExpenseCreate,
    ExpenseResponse,
    HealthResponse,
    LocationPoiResponse,
    PlaceCandidateResponse,
    PlaceSearchResultResponse,
    PlanningBudgetResponse,
    PlanningContextResponse,
    PlanningIntentParseRequest,
    PlanningIntentResolution,
    PlanningRunCreate,
    PlanningRunDecision,
    RejectPlanRevisionRequest,
    PlanningRunExecutionResponse,
    PlanningRunResponse,
    PlanRevisionResponse,
    RouteRecalculateRequest,
    TripCreate,
    TripDeletionPreviewResponse,
    TripResponse,
    TripPreferencesResponse,
    TripPreferencesUpdate,
    TripUpdate,
    TripExecutionActionRequest,
    ExtendStayRequest,
    ExtendStayResponse,
    LeaveEarlyRequest,
    LeaveEarlyResponse,
    DynamicReplanRequest,
    TripExecutionResponse,
    TripExecutionStart,
    NavigationLocationUpdate,
    NavigationObservation,
    NavigationObservationResponse,
    NavigationSessionActionRequest,
    NavigationSessionCreate,
    NavigationSessionResponse,
    NavigationStartRequest,
    NavigationStartResponse,
    ExecutionReadModelResponse,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await engine.dispose()
    if hasattr(app.state, "content_engine"):
        app.state.content_engine.dispose()


settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)
from app.arrangement_routes import router as arrangement_router
from app.arrangement_service import ArrangementConstraintError
app.include_router(arrangement_router)


@app.exception_handler(ArrangementConstraintError)
async def arrangement_conflict_handler(request, exc):
    return JSONResponse(status_code=422, content={"detail": {"code": "arrangement_conflict", "message": str(exc)}})


@app.exception_handler(FormalWriteConflictError)
async def formal_write_conflict_handler(request, exc):
    return JSONResponse(status_code=409, content={"detail": {"code": "trip_version_conflict", "message": str(exc)}})


from app.planner_repository import recalculate_formal_route
from app.assistant_routes import router as assistant_router
app.include_router(assistant_router)
from app.saved_intentions import router as saved_intentions_router
app.include_router(saved_intentions_router)
from app.agent_monitor import router as agent_monitor_router
app.include_router(agent_monitor_router)

if (os.environ.get("ROAMSYNC_LOCAL_PRODUCT") == "1"
        or os.environ.get("ROAMSYNC_ISOLATED_INTEGRATION") == "1"):
    from app.integration_runtime import install_content
    install_content(app, settings)


def map_provider_http_error(exc: MapProviderError) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code,
        detail={
            "code": exc.code,
            "message": str(exc),
            "provider": "amap",
            "provider_code": exc.provider_code,
        },
    )


@app.get("/health/live", response_model=HealthResponse, tags=["health"])
async def live() -> HealthResponse:
    return HealthResponse(status="ok")


@app.get("/health/ready", response_model=HealthResponse, tags=["health"])
async def ready(session: AsyncSession = Depends(get_session)) -> HealthResponse:
    try:
        await session.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database is unavailable",
        ) from exc
    return HealthResponse(status="ready")


@app.post(
    "/api/v1/trips",
    response_model=TripResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["trips"],
)
async def create_trip_endpoint(
    payload: TripCreate,
    session: AsyncSession = Depends(get_session),
) -> TripResponse:
    trip = await create_trip(session, payload)
    return TripResponse.model_validate(trip)


@app.get("/api/v1/trips", response_model=list[TripResponse], tags=["trips"])
async def list_trips_endpoint(
    session: AsyncSession = Depends(get_session),
) -> list[TripResponse]:
    return [TripResponse.model_validate(trip) for trip in await list_trips(session)]


@app.get(
    "/api/v1/locations/cities",
    response_model=list[CitySuggestionResponse],
    tags=["locations"],
)
async def search_cities_endpoint(
    keyword: str = Query(min_length=1, max_length=40),
) -> list[CitySuggestionResponse]:
    try:
        return await search_amap_cities(keyword)
    except MapProviderError as exc:
        raise map_provider_http_error(exc) from exc


@app.get(
    "/api/v1/locations/pois",
    response_model=list[LocationPoiResponse],
    tags=["locations"],
)
async def search_location_pois_endpoint(
    keyword: str = Query(min_length=1, max_length=80),
    city: str = Query(min_length=1, max_length=40),
    accommodation_only: bool = Query(default=False),
) -> list[LocationPoiResponse]:
    try:
        return await search_amap_location_pois(keyword, city, accommodation_only)
    except MapProviderError as exc:
        raise map_provider_http_error(exc) from exc


@app.get(
    "/api/v1/trips/{trip_id}", response_model=TripResponse, tags=["trips"]
)
async def get_trip_endpoint(
    trip_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> TripResponse:
    try:
        trip = await get_trip(session, trip_id)
    except TripNotFoundError as exc:
        raise HTTPException(status_code=404, detail="trip not found") from exc
    return TripResponse.model_validate(trip)


@app.get(
    "/api/v1/trips/{trip_id}/preferences",
    response_model=TripPreferencesResponse,
    tags=["planning"],
)
async def get_trip_preferences_endpoint(
    trip_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> TripPreferencesResponse:
    try:
        preferences = await get_trip_preferences(session, trip_id)
    except TripNotFoundError as exc:
        raise HTTPException(status_code=404, detail="trip not found") from exc
    return TripPreferencesResponse.model_validate(preferences)


@app.put(
    "/api/v1/trips/{trip_id}/preferences",
    response_model=TripPreferencesResponse,
    tags=["planning"],
)
async def update_trip_preferences_endpoint(
    trip_id: uuid.UUID,
    payload: TripPreferencesUpdate,
    session: AsyncSession = Depends(get_session),
) -> TripPreferencesResponse:
    try:
        preferences = await update_trip_preferences(session, trip_id, payload)
    except TripNotFoundError as exc:
        raise HTTPException(status_code=404, detail="trip not found") from exc
    except TripPreferencesVersionConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail="trip preferences were updated elsewhere; reload and retry",
        ) from exc
    return TripPreferencesResponse.model_validate(preferences)


@app.get(
    "/api/v1/trips/{trip_id}/planning-context",
    response_model=PlanningContextResponse,
    tags=["planning"],
)
async def get_planning_context_endpoint(
    trip_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> PlanningContextResponse:
    try:
        return await build_planning_context(session, trip_id)
    except TripNotFoundError as exc:
        raise HTTPException(status_code=404, detail="trip not found") from exc


@app.post(
    "/api/v1/trips/{trip_id}/planning-intent/resolve",
    response_model=PlanningIntentResolution,
    tags=["planning"],
)
async def resolve_planning_intent_endpoint(
    trip_id: uuid.UUID,
    payload: PlanningIntentParseRequest,
    session: AsyncSession = Depends(get_session),
) -> PlanningIntentResolution:
    try:
        from app.planning_preparation import resolve_planning_without_transaction
        resolution, _, _ = await resolve_planning_without_transaction(
            session,
            trip_id,
            payload,
            semantic_provider=build_semantic_intent_provider(get_settings()),
        )
        return resolution
    except TripNotFoundError as exc:
        raise HTTPException(status_code=404, detail="trip not found") from exc
    except IntentContextError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": exc.code, "message": exc.message},
        ) from exc


@app.post(
    "/api/v1/trips/{trip_id}/planning-runs",
    response_model=PlanningRunResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["planning"],
)
async def create_planning_run_endpoint(
    trip_id: uuid.UUID,
    payload: PlanningRunCreate,
    session: AsyncSession = Depends(get_session),
) -> PlanningRunResponse:
    try:
        run = await create_planning_run(
            session,
            trip_id,
            payload,
            semantic_provider=build_semantic_intent_provider(get_settings()),
        )
    except TripNotFoundError as exc:
        raise HTTPException(status_code=404, detail="trip not found") from exc
    except IntentContextError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    except UnsupportedPlanningIntentError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "unsupported_planning_route", "route": exc.route, "message": exc.message},
        ) from exc
    except RecoveryPlanningConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except StalePlanningRunError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return PlanningRunResponse.model_validate(run)


@app.get(
    "/api/v1/trips/{trip_id}/planning-runs",
    response_model=list[PlanningRunResponse],
    tags=["planning"],
)
async def list_planning_runs_endpoint(
    trip_id: uuid.UUID,
    limit: int = Query(default=20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
) -> list[PlanningRunResponse]:
    try:
        return [PlanningRunResponse.model_validate(item) for item in await list_planning_runs(session, trip_id, limit=limit)]
    except TripNotFoundError as exc:
        raise HTTPException(status_code=404, detail="trip not found") from exc


@app.get(
    "/api/v1/trips/{trip_id}/execution",
    response_model=TripExecutionResponse,
    tags=["execution"],
)
async def get_trip_execution_endpoint(
    trip_id: uuid.UUID, session: AsyncSession = Depends(get_session)
) -> TripExecutionResponse:
    try:
        return await get_trip_execution(session, trip_id)
    except TripNotFoundError as exc:
        raise HTTPException(status_code=404, detail="trip not found") from exc


@app.get("/api/v1/trips/{trip_id}/execution-progress", response_model=ExecutionReadModelResponse, tags=["execution"])
async def get_execution_progress_endpoint(trip_id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> ExecutionReadModelResponse:
    try:
        return await get_execution_read_model(session, trip_id)
    except TripNotFoundError as exc:
        raise HTTPException(status_code=404, detail="trip not found") from exc


@app.post(
    "/api/v1/trips/{trip_id}/execution/start",
    response_model=TripExecutionResponse,
    tags=["execution"],
)
async def start_trip_execution_endpoint(
    trip_id: uuid.UUID,
    payload: TripExecutionStart,
    session: AsyncSession = Depends(get_session),
) -> TripExecutionResponse:
    try:
        return await start_trip_execution(session, trip_id, payload)
    except TripNotFoundError as exc:
        raise HTTPException(status_code=404, detail="trip not found") from exc
    except InvalidTripExecutionStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post(
    "/api/v1/trips/{trip_id}/navigation/start",
    response_model=NavigationStartResponse,
    tags=["navigation", "execution"],
)
async def start_navigation_endpoint(
    trip_id: uuid.UUID,
    payload: NavigationStartRequest,
    session: AsyncSession = Depends(get_session),
) -> NavigationStartResponse:
    try:
        return await start_navigation(session, trip_id, payload)
    except TripNotFoundError as exc:
        raise HTTPException(status_code=404, detail="trip not found") from exc
    except (NavigationStartConflictError, NavigationSessionConflictError, NavigationSessionStateError, InvalidTripExecutionStateError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post(
    "/api/v1/trips/{trip_id}/navigation-sessions",
    response_model=NavigationSessionResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["navigation"],
)
async def create_navigation_session_endpoint(
    trip_id: uuid.UUID,
    payload: NavigationSessionCreate,
    session: AsyncSession = Depends(get_session),
) -> NavigationSessionResponse:
    try:
        return navigation_session_response(
            await create_navigation_session(session, trip_id, payload)
        )
    except NavigationSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (NavigationSessionConflictError, NavigationSessionStateError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get(
    "/api/v1/navigation-sessions/{navigation_session_id}",
    response_model=NavigationSessionResponse,
    tags=["navigation"],
)
async def get_navigation_session_endpoint(
    navigation_session_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> NavigationSessionResponse:
    try:
        return navigation_session_response(await get_navigation_session(session, navigation_session_id))
    except NavigationSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post(
    "/api/v1/navigation-sessions/{navigation_session_id}/location-updates",
    response_model=NavigationSessionResponse,
    tags=["navigation"],
)
async def update_navigation_location_endpoint(
    navigation_session_id: uuid.UUID,
    payload: NavigationLocationUpdate,
    session: AsyncSession = Depends(get_session),
) -> NavigationSessionResponse:
    try:
        return navigation_session_response(
            await apply_location_update(session, navigation_session_id, payload)
        )
    except NavigationSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (NavigationSessionStateError, StaleNavigationWriteError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post(
    "/api/v1/navigation-observations",
    response_model=NavigationObservationResponse,
    tags=["navigation"],
)
async def ingest_navigation_observation_endpoint(
    payload: NavigationObservation,
    session: AsyncSession = Depends(get_session),
) -> NavigationObservationResponse:
    try:
        return await ingest_navigation_observation(session, payload)
    except NavigationObservationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except NavigationObservationConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post(
    "/api/v1/navigation-sessions/{navigation_session_id}/actions",
    response_model=NavigationSessionResponse,
    tags=["navigation"],
)
async def apply_navigation_session_action_endpoint(
    navigation_session_id: uuid.UUID,
    payload: NavigationSessionActionRequest,
    session: AsyncSession = Depends(get_session),
) -> NavigationSessionResponse:
    try:
        return navigation_session_response(
            await apply_navigation_session_action(session, navigation_session_id, payload)
        )
    except NavigationSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except NavigationSessionStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post(
    "/api/v1/navigation-sessions/{navigation_session_id}/route-refresh",
    response_model=NavigationSessionResponse,
    tags=["navigation"],
)
async def refresh_navigation_route_endpoint(
    navigation_session_id: uuid.UUID,
) -> NavigationSessionResponse:
    # Phase 2 intentionally exposes no real map adapter.  This endpoint proves
    # the service boundary while returning a stable configuration failure.
    try:
        item = await refresh_route(session_factory, navigation_session_id, UnavailableRoutingProvider())
        return navigation_session_response(item)
    except NavigationSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (NavigationSessionStateError, StaleNavigationWriteError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RoutingProviderError as exc:
        raise HTTPException(status_code=503, detail={"code": exc.code, "message": str(exc)}) from exc


@app.post(
    "/api/v1/trip-executions/{execution_id}/actions",
    response_model=TripExecutionResponse,
    tags=["execution"],
)
async def apply_trip_execution_action_endpoint(
    execution_id: uuid.UUID,
    payload: TripExecutionActionRequest,
    session: AsyncSession = Depends(get_session),
) -> TripExecutionResponse:
    try:
        return await apply_trip_execution_action(session, execution_id, payload)
    except TripExecutionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="trip execution not found") from exc
    except InvalidTripExecutionStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/v1/activity-executions/{activity_execution_id}/extend-stay", response_model=ExtendStayResponse, tags=["execution"])
async def extend_stay_endpoint(activity_execution_id: uuid.UUID, payload: ExtendStayRequest, session: AsyncSession = Depends(get_session)) -> ExtendStayResponse:
    try:
        response = await extend_stay(session, activity_execution_id, payload)
        run = await ensure_experience_recovery(session, activity_execution_id)
        response.replanning_status = run.status if run else "not_required"
        return response
    except TripExecutionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="activity execution not found") from exc
    except InvalidTripExecutionStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/v1/activity-executions/{activity_execution_id}/leave-early", response_model=LeaveEarlyResponse, tags=["execution"])
async def leave_early_endpoint(activity_execution_id: uuid.UUID, payload: LeaveEarlyRequest, session: AsyncSession = Depends(get_session)) -> LeaveEarlyResponse:
    try:
        return await leave_early(session, activity_execution_id, payload)
    except TripExecutionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="activity execution not found") from exc
    except InvalidTripExecutionStateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post(
    "/api/v1/trips/{trip_id}/execution/replan",
    response_model=DynamicReplanResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["execution", "planning"],
)
async def request_dynamic_replan_endpoint(
    trip_id: uuid.UUID,
    payload: DynamicReplanRequest,
    session: AsyncSession = Depends(get_session),
) -> DynamicReplanResponse:
    try:
        run, event_id = await request_dynamic_replan(session, trip_id, payload)
    except TripExecutionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="trip execution not found") from exc
    except (InvalidTripExecutionStateError, UnsupportedPlanningIntentError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return DynamicReplanResponse(run=PlanningRunResponse.model_validate(run), trigger_event_id=event_id)


@app.get(
    "/api/v1/planning-runs/{run_id}",
    response_model=PlanningRunResponse,
    tags=["planning"],
)
async def get_planning_run_endpoint(
    run_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> PlanningRunResponse:
    try:
        run = await get_planning_run(session, run_id)
    except PlanningRunNotFoundError as exc:
        raise HTTPException(status_code=404, detail="planning run not found") from exc
    return PlanningRunResponse.model_validate(run)


@app.post(
    "/api/v1/planning-runs/{run_id}/decision",
    response_model=PlanningRunExecutionResponse,
    tags=["planning"],
)
async def decide_planning_run_endpoint(
    run_id: uuid.UUID,
    payload: PlanningRunDecision,
    session: AsyncSession = Depends(get_session),
) -> PlanningRunExecutionResponse:
    try:
        execution = await execute_planning_run(run_id, decision=payload)
        run = await get_planning_run(session, run_id)
        await session.refresh(run)
    except PlanningRunNotFoundError as exc:
        raise HTTPException(status_code=404, detail="planning run not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return PlanningRunExecutionResponse(
        run=PlanningRunResponse.model_validate(run),
        pending_interrupt=execution.pending_interrupt,
    )


@app.get(
    "/api/v1/planning-runs/{run_id}/revision",
    response_model=PlanRevisionResponse,
    tags=["planning"],
)
async def get_plan_revision_endpoint(
    run_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> PlanRevisionResponse:
    try:
        revision = await get_latest_revision(session, run_id)
    except PlanningRunNotFoundError as exc:
        raise HTTPException(status_code=404, detail="planning run not found") from exc
    except PlanRevisionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="planning revision not ready") from exc
    return PlanRevisionResponse.model_validate(revision)


@app.post(
    "/api/v1/plan-revisions/{revision_id}/reject",
    response_model=PlanRevisionResponse,
    tags=["planning"],
)
async def reject_plan_revision_endpoint(
    revision_id: uuid.UUID,
    payload: RejectPlanRevisionRequest | None = None,
    session: AsyncSession = Depends(get_session),
) -> PlanRevisionResponse:
    try:
        revision = await reject_revision(
            session, revision_id,
            reason_code=payload.reason_code if payload else None,
            reason_text=payload.reason_text if payload else None,
        )
    except PlanRevisionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="planning revision not found") from exc
    except InvalidPlanningRunStateError as exc:
        raise HTTPException(status_code=409, detail="planning revision is no longer pending") from exc
    return PlanRevisionResponse.model_validate(revision)


@app.post(
    "/api/v1/plan-revisions/{revision_id}/accept",
    response_model=PlanRevisionResponse,
    tags=["planning"],
)
async def accept_plan_revision_endpoint(
    revision_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> PlanRevisionResponse:
    try:
        revision = await accept_plan_revision(session, revision_id)
    except PlanRevisionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="planning revision not found") from exc
    except StalePlanningRunError as exc:
        raise HTTPException(status_code=409, detail="formal trip changed after planning started") from exc
    except InvalidPlanningRunStateError as exc:
        raise HTTPException(status_code=409, detail="planning revision is no longer pending") from exc
    except InvalidPlanRevisionError as exc:
        raise HTTPException(status_code=422, detail=exc.result.model_dump(mode="json")) from exc
    return PlanRevisionResponse.model_validate(revision)


@app.put("/api/v1/trips/{trip_id}", response_model=TripResponse, tags=["trips"])
async def update_trip_endpoint(
    trip_id: uuid.UUID,
    payload: TripUpdate,
    session: AsyncSession = Depends(get_session),
) -> TripResponse:
    try:
        trip = await update_trip(session, trip_id, payload)
    except TripNotFoundError as exc:
        raise HTTPException(status_code=404, detail="trip not found") from exc
    except TripVersionConflictError as exc:
        raise HTTPException(status_code=409, detail="trip was updated elsewhere; reload and retry") from exc
    except TripDateConflictError as exc:
        raise HTTPException(status_code=409, detail="date change would remove days containing activities") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return TripResponse.model_validate(trip)


@app.post(
    "/api/v1/trips/{trip_id}/duplicate",
    response_model=TripResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["trips"],
)
async def duplicate_trip_endpoint(
    trip_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> TripResponse:
    try:
        return TripResponse.model_validate(await duplicate_trip(session, trip_id))
    except TripNotFoundError as exc:
        raise HTTPException(status_code=404, detail="trip not found") from exc


@app.post("/api/v1/trips/{trip_id}/archive", response_model=TripResponse, tags=["trips"])
async def archive_trip_endpoint(
    trip_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> TripResponse:
    try:
        return TripResponse.model_validate(await archive_trip(session, trip_id))
    except TripNotFoundError as exc:
        raise HTTPException(status_code=404, detail="trip not found") from exc


@app.get(
    "/api/v1/trips/{trip_id}/deletion-preview",
    response_model=TripDeletionPreviewResponse,
    tags=["trips"],
)
async def trip_deletion_preview_endpoint(
    trip_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> TripDeletionPreviewResponse:
    try:
        return await get_trip_deletion_preview(session, trip_id)
    except TripNotFoundError as exc:
        raise HTTPException(status_code=404, detail="trip not found") from exc


@app.delete("/api/v1/trips/{trip_id}", status_code=204, tags=["trips"])
async def delete_trip_endpoint(
    trip_id: uuid.UUID,
    confirm: bool = Query(default=False),
    session: AsyncSession = Depends(get_session),
) -> Response:
    if not confirm:
        raise HTTPException(status_code=400, detail="confirm=true is required")
    try:
        await delete_trip(session, trip_id)
    except TripNotFoundError as exc:
        raise HTTPException(status_code=404, detail="trip not found") from exc
    return Response(status_code=204)


@app.post(
    "/api/v1/trips/{trip_id}/expenses",
    response_model=ExpenseResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["expenses"],
)
async def create_expense_endpoint(
    trip_id: uuid.UUID,
    payload: ExpenseCreate,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> ExpenseResponse:
    try:
        expense, duplicate = await create_expense(session, trip_id, payload)
    except TripNotFoundError as exc:
        raise HTTPException(status_code=404, detail="trip not found") from exc
    except IdempotencyConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="idempotency key was already used with a different payload",
        ) from exc
    if duplicate:
        response.status_code = status.HTTP_200_OK
    result = ExpenseResponse.model_validate(expense)
    return result.model_copy(update={"duplicate": duplicate})


@app.get(
    "/api/v1/trips/{trip_id}/budget",
    response_model=BudgetResponse,
    tags=["budgets"],
)
async def get_budget_endpoint(
    trip_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> BudgetResponse:
    try:
        return await get_budget(session, trip_id)
    except TripNotFoundError as exc:
        raise HTTPException(status_code=404, detail="trip not found") from exc


@app.get(
    "/api/v1/trips/{trip_id}/days",
    response_model=list[DayPlanResponse],
    tags=["planner"],
)
async def get_day_plans_endpoint(
    trip_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> list[DayPlanResponse]:
    try:
        return await get_day_plans(session, trip_id)
    except TripNotFoundError as exc:
        raise HTTPException(status_code=404, detail="trip not found") from exc


@app.get(
    "/api/v1/trips/{trip_id}/candidates",
    response_model=list[PlaceCandidateResponse],
    tags=["planner"],
)
async def get_candidates_endpoint(
    trip_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> list[PlaceCandidateResponse]:
    try:
        return await get_candidates(session, trip_id)
    except TripNotFoundError as exc:
        raise HTTPException(status_code=404, detail="trip not found") from exc


@app.get(
    "/api/v1/trips/{trip_id}/places/search",
    response_model=list[PlaceSearchResultResponse],
    tags=["planner"],
)
async def search_places_endpoint(
    trip_id: uuid.UUID,
    q: str = Query(min_length=1, max_length=80),
    category: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> list[PlaceSearchResultResponse]:
    try:
        trip = await get_trip(session, trip_id)
        return await search_amap_places(
            q,
            trip.destination_adcode or trip.destination,
            category,
        )
    except TripNotFoundError as exc:
        raise HTTPException(status_code=404, detail="trip not found") from exc
    except MapProviderError as exc:
        raise map_provider_http_error(exc) from exc


@app.get(
    "/api/v1/trips/{trip_id}/planning-budget",
    response_model=PlanningBudgetResponse,
    tags=["planner"],
)
async def get_planning_budget_endpoint(
    trip_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> PlanningBudgetResponse:
    try:
        return await get_planning_budget(session, trip_id)
    except TripNotFoundError as exc:
        raise HTTPException(status_code=404, detail="trip not found") from exc


@app.post(
    "/api/v1/day-plans/{day_plan_id}/activities",
    response_model=ActivityResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["planner"],
)
async def add_activity_endpoint(
    day_plan_id: uuid.UUID,
    payload: ActivityCreate,
    session: AsyncSession = Depends(get_session),
    trip_version: int | None = Header(default=None, alias="X-Trip-Version", gt=0),
) -> ActivityResponse:
    try:
        return await add_activity(
            session,
            day_plan_id,
            payload.place_id,
            payload.place_snapshot,
            payload.importance,
            payload.can_skip,
            payload.minimum_duration_minutes,
            "importance" in payload.model_fields_set,
            "can_skip" in payload.model_fields_set,
            expected_trip_version=trip_version,
        )
    except DayPlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail="day plan not found") from exc
    except PlaceCandidateNotFoundError as exc:
        raise HTTPException(status_code=404, detail="place candidate not found") from exc
    except DuplicatePlaceError as exc:
        raise HTTPException(status_code=409, detail="place is already in this trip") from exc
    except ActivityDecisionSemanticsError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except MapProviderError as exc:
        raise map_provider_http_error(exc) from exc


@app.put(
    "/api/v1/day-plans/{day_plan_id}/activity-order",
    response_model=DayPlanResponse,
    tags=["planner"],
)
async def reorder_activities_endpoint(
    day_plan_id: uuid.UUID,
    payload: ActivityOrderUpdate,
    session: AsyncSession = Depends(get_session),
    trip_version: int | None = Header(default=None, alias="X-Trip-Version", gt=0),
) -> DayPlanResponse:
    try:
        return await reorder_activities(session, day_plan_id, payload.activity_ids, expected_trip_version=trip_version)
    except DayPlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail="day plan not found") from exc
    except InvalidActivityOrderError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="activity_ids must exactly match the activities in this day",
        ) from exc
    except MapProviderError as exc:
        raise map_provider_http_error(exc) from exc


@app.put(
    "/api/v1/activities/{activity_id}",
    response_model=ActivityResponse,
    tags=["planner"],
)
async def update_activity_endpoint(
    activity_id: uuid.UUID,
    payload: ActivityUpdate,
    session: AsyncSession = Depends(get_session),
    trip_version: int | None = Header(default=None, alias="X-Trip-Version", gt=0),
) -> ActivityResponse:
    try:
        return await update_activity(session, activity_id, payload, expected_trip_version=trip_version)
    except ActivityNotFoundError as exc:
        raise HTTPException(status_code=404, detail="activity not found") from exc
    except ActivityVersionConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "activity_version_conflict",
                "message": "活动已被其他操作修改，请重新加载后再保存",
            },
        ) from exc
    except ActivityDecisionSemanticsError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post(
    "/api/v1/activities/{activity_id}/move",
    response_model=ActivityMoveResponse,
    tags=["planner"],
)
async def move_activity_endpoint(
    activity_id: uuid.UUID,
    payload: ActivityMoveRequest,
    session: AsyncSession = Depends(get_session),
    trip_version: int | None = Header(default=None, alias="X-Trip-Version", gt=0),
) -> ActivityMoveResponse:
    try:
        return await move_activity(session, activity_id, payload, expected_trip_version=trip_version)
    except ActivityNotFoundError as exc:
        raise HTTPException(status_code=404, detail="activity not found") from exc
    except DayPlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail="day plan not found") from exc
    except ActivityVersionConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "activity_version_conflict", "message": "活动已被其他操作修改，请重新加载后再移动"},
        ) from exc
    except DuplicatePlaceError as exc:
        raise HTTPException(status_code=409, detail="place is already in the target day") from exc
    except InvalidActivityMoveError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="target day or position is invalid for this activity",
        ) from exc
    except MapProviderError as exc:
        raise map_provider_http_error(exc) from exc


@app.post(
    "/api/v1/day-plans/{day_plan_id}/route",
    response_model=DayPlanResponse,
    tags=["planner"],
)
async def recalculate_route_endpoint(
    day_plan_id: uuid.UUID,
    payload: RouteRecalculateRequest,
    session: AsyncSession = Depends(get_session),
    trip_version: int | None = Header(default=None, alias="X-Trip-Version", gt=0),
) -> DayPlanResponse:
    try:
        return await recalculate_formal_route(session, day_plan_id, payload.mode, expected_trip_version=trip_version, adjust_times=payload.adjust_times)
    except DayPlanNotFoundError as exc:
        raise HTTPException(status_code=404, detail="day plan not found") from exc
    except MapProviderError as exc:
        raise map_provider_http_error(exc) from exc


@app.get("/api/v1/day-plans/{day_plan_id}/route", tags=["planner"])
async def query_route_endpoint(day_plan_id: uuid.UUID, mode: str = Query(default="walk", pattern="^(walk|driving|transit)$"), session: AsyncSession = Depends(get_session)):
    from app.planner_repository import query_formal_route
    try:
        version, legs = await query_formal_route(session, day_plan_id, mode)
        return {"trip_version": version, "mode": mode, "legs": [vars(leg) for leg in legs]}
    except DayPlanNotFoundError as exc:
        raise HTTPException(404, "day plan not found") from exc
    except MapProviderError as exc:
        raise map_provider_http_error(exc) from exc


@app.delete(
    "/api/v1/activities/{activity_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["planner"],
)
async def delete_activity_endpoint(
    activity_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    trip_version: int | None = Header(default=None, alias="X-Trip-Version", gt=0),
) -> Response:
    try:
        await delete_activity(session, activity_id, expected_trip_version=trip_version)
    except ActivityNotFoundError as exc:
        raise HTTPException(status_code=404, detail="activity not found") from exc
    except MapProviderError as exc:
        raise map_provider_http_error(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post(
    "/api/v1/demo/reset",
    response_model=DemoResetResponse,
    tags=["planner"],
)
async def reset_demo_endpoint(
    session: AsyncSession = Depends(get_session),
) -> DemoResetResponse:
    if settings.app_env not in {"development", "test"}:
        raise HTTPException(status_code=404, detail="not found")
    await seed_demo_data(session, reset=True)
    return DemoResetResponse(trip_id=DEMO_TRIP_ID, status="reset")
