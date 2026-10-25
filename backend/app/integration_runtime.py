"""Controlled local integration boundary; never enabled implicitly in production."""
import hmac
import os
from fastapi import HTTPException, Request
from sqlalchemy import create_engine
from starlette.responses import JSONResponse
from app.place_content.provider import AMapContentProvider
from app.place_content.repository import ContentRepository
from app.place_content.routes import create_router
from app.place_content.service import PlaceContentService
from app.mobile_access import DeviceSessions, create_device_router


def install_content(app, settings):
    token = os.environ.get("ROAMSYNC_INTEGRATION_TOKEN", "")
    owner = os.environ.get("ROAMSYNC_INTEGRATION_OWNER", "")
    if not token or not owner:
        raise RuntimeError("Controlled integration requires a server token and owner")
    sync_engine = create_engine(settings.database_url, pool_pre_ping=True)
    service = PlaceContentService(AMapContentProvider(settings.amap_rest_key), ContentRepository(sync_engine))

    device_sessions = DeviceSessions(owner)
    origins = {value.strip() for value in os.environ.get("ROAMSYNC_LOCAL_ORIGINS", "http://127.0.0.1:3000,http://localhost:3000").split(",") if value.strip()}
    def server_authorized(request):
        return hmac.compare_digest(request.headers.get("x-roamsync-access", ""), token)

    @app.middleware("http")
    async def local_boundary(request: Request, call_next):
        if request.url.path.startswith("/api/"):
            origin = request.headers.get("origin")
            is_pair_exchange = request.url.path == "/api/v1/device-sessions" and request.method == "POST"
            authenticated_owner = owner if server_authorized(request) else device_sessions.authenticate(request.headers.get("authorization"))
            if not authenticated_owner and not is_pair_exchange:
                return JSONResponse({"detail": {"code": "unauthorized", "message": "请通过本地 RoamSync 页面访问"}}, status_code=401)
            if origin and origin not in origins:
                return JSONResponse({"detail": {"code": "origin_denied"}}, status_code=403)
            if request.headers.get("sec-fetch-site") == "cross-site":
                return JSONResponse({"detail": {"code": "origin_denied"}}, status_code=403)
            request.state.authenticated_owner = authenticated_owner
        return await call_next(request)

    def trusted_owner(request: Request):
        if not getattr(request.state, "authenticated_owner", None):
            raise HTTPException(401, "unauthorized")
        return request.state.authenticated_owner

    app.state.place_content_service = service
    app.state.content_engine = sync_engine
    app.state.trusted_owner_dependency = trusted_owner
    app.state.device_sessions = device_sessions
    app.include_router(create_device_router(device_sessions, server_authorized))
    from app.place_content.reference_images import PlaceReferenceImages
    app.include_router(create_router(service, trusted_owner,
        reference_images=PlaceReferenceImages(service.provider, settings)))

    from app.drafts.repository import DraftRepository
    from app.drafts.service import DraftService, ModelDraftGenerator
    from app.drafts.routes import create_router as create_draft_router
    draft_service = DraftService(DraftRepository(sync_engine), ModelDraftGenerator(settings, service))
    app.state.draft_service = draft_service

    from app.database import session_factory
    from app.draft_promotion.service import DraftPromotionService
    from app.draft_promotion.routes import create_router as create_promotion_router
    promotion_service = DraftPromotionService(draft_service.repository, session_factory, service)
    app.state.draft_promotion_service = promotion_service
    app.include_router(create_promotion_router(promotion_service, trusted_owner))
    # Specific promotion-preview must precede Draft's /{draft_id}/{action} route.
    app.include_router(create_draft_router(draft_service, trusted_owner))

    from app.travel_preferences.service import PreferenceService
    from app.travel_preferences.routes import create_router as create_preference_router
    preference_service = PreferenceService(sync_engine, service)
    app.state.preference_service = preference_service
    app.include_router(create_preference_router(preference_service, trusted_owner))

    from app.requirement_routes import create_router as create_requirement_router
    app.include_router(create_requirement_router(trusted_owner))
