"""Initialize ONLY the explicitly named isolated integration database."""
import os
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from app.config import get_settings
from app.place_content.repository import metadata
from app.drafts.repository import metadata as draft_metadata
from app.travel_preferences.service import metadata as preference_metadata
from app.draft_promotion.repository import metadata as promotion_metadata

if __name__ == "__main__":
    settings = get_settings()
    url = make_url(settings.database_url)
    if os.environ.get("ROAMSYNC_ISOLATED_INTEGRATION") != "1" or url.host != "postgres" or url.database != "roamsync_v2_integration":
        raise RuntimeError("Refusing non-isolated content initialization")
    engine = create_engine(url)
    metadata.create_all(engine)
    draft_metadata.create_all(engine)
    preference_metadata.create_all(engine)
    promotion_metadata.create_all(engine)
    from app.drafts.repository import DraftRepository
    DraftRepository(engine).recover_interrupted()
    engine.dispose()
    print("Isolated content tables ready")
