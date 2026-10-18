"""Read-only real provider smoke; synthetic owner and in-memory SQLite only."""
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from dotenv import dotenv_values
from sqlalchemy import create_engine, inspect
from sqlalchemy.pool import StaticPool
from app.place_content.provider import AMapContentProvider
from app.place_content.repository import ContentRepository, metadata as content_metadata
from app.place_content.service import PlaceContentService
from app.travel_preferences.contracts import DiscoveryQuery, TravelPreferences
from app.travel_preferences.service import PreferenceService, metadata

async def main():
    key = dotenv_values(sys.argv[1]).get("AMAP_REST_KEY", "")
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread":False})
    content_metadata.create_all(engine); metadata.create_all(engine)
    service = PreferenceService(engine, PlaceContentService(AMapContentProvider(key), ContentRepository(engine)))
    service.save("synthetic-b-smoke", TravelPreferences(preferred_categories=["food"], interests=["茶"]))
    report = {"at":datetime.now(UTC).isoformat(), "provider":"amap", "fixture":False,"formal_database_imported":False,"checks":[]}
    for label, query in [("city_categories", DiscoveryQuery(city="杭州")),
        ("nearby", DiscoveryQuery(city="杭州", category="food", center={"longitude":120.15,"latitude":30.25,"coordinate_system":"GCJ02"},radius_meters=1000)),
        ("rating_food_price", DiscoveryQuery(city="杭州", category="food", query="茶馆",min_rating=4,max_food_price_yuan=100,include_unknown=False))]:
        try:
            result = await service.discover("synthetic-b-smoke",query)
            report["checks"].append({"check":label,"status":result.status,"count":len(result.items),"preference_applied":result.preference_applied,
                "sample":[{"id":str(item.place.ref.place_id),"name":item.place.name,"category":item.place.category,"rating":item.place.rating,"price":item.place.price.model_dump() if item.place.price else None,"reasons":item.reasons} for item in result.items[:3]]})
        except Exception as error:
            report["checks"].append({"check":label,"error_type":type(error).__name__,"code":getattr(error,"code",None)})
    report["formal_database_imported"] = "app.database" in sys.modules
    report["tables"] = inspect(engine).get_table_names()
    target = Path(sys.argv[2]);target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"checks":[{key:value for key,value in item.items() if key != "sample"} for item in report["checks"]]}))
    engine.dispose()

if __name__ == "__main__": asyncio.run(main())
