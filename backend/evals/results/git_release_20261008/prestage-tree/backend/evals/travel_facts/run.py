"""python -m evals.travel_facts.run --output PATH (offline deterministic)."""
import argparse
import asyncio
import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.travel_facts.adapters import AMapPoiAdapter, AMapRouteAdapter, WeatherForecastAdapter
from app.travel_facts.execution import ExecutionFactAdapter
from app.travel_facts.interfaces import ProviderUnavailable
from app.travel_facts.models import FactRequirement, FactType, StatusValue, TimeScope
from app.travel_facts.repository import InMemoryFactRepository
from app.travel_facts.service import TravelFactService
from .fixtures import (NOW, FixtureExecutionReader, FixtureProvider, canonical_subject, destination,
                       place, policies, poi_fixture, route, synthetic_bundle, weather_fixture)


def subset(expected, actual):
    return all(key in actual and (subset(value,actual[key]) if isinstance(value,dict) else value==actual[key])
               for key,value in expected.items())


async def scenario(case_id):
    freshness,authority=policies(); repository=InMemoryFactRepository()
    req=FactRequirement(fact_type="place.operational_status",subject=place())
    providers=[]
    async def seed(*bundles):
        for bundle in bundles:
            await repository.merge(bundle)
    if case_id in {"fresh_status","stale_status","stale_background","provider_unknown","exact_retry","future_current_status_gap"}:
        if case_id=="stale_background": req=req.model_copy(update={"allow_stale":True})
        if case_id=="future_current_status_gap": req=req.model_copy(update={"time_scope":TimeScope(start=NOW+timedelta(hours=1))})
        bundle=synthetic_bundle(req,retrieved_at=NOW-timedelta(seconds=61) if case_id.startswith("stale") else NOW,
            value=StatusValue(status="unknown" if case_id=="provider_unknown" else "closed"))
        await seed(bundle)
        if case_id=="exact_retry": await seed(bundle)
    elif case_id in {"expired_notice","future_notice"}:
        await seed(synthetic_bundle(req,effective_from=NOW-timedelta(hours=1) if case_id=="expired_notice" else NOW+timedelta(hours=1),
            effective_until=NOW if case_id=="expired_notice" else NOW+timedelta(hours=2)))
    elif case_id=="equal_authority_conflict":
        await seed(synthetic_bundle(req),synthetic_bundle(req,provider="fixture_peer",value=StatusValue(status="open")))
    elif case_id=="official_temporary_closure":
        await seed(synthetic_bundle(req,source_type="official_schedule",value=StatusValue(status="open")),
            synthetic_bundle(req,effective_from=NOW-timedelta(minutes=1),effective_until=NOW+timedelta(hours=1)))
    elif case_id=="stale_official_fresh_map":
        await seed(synthetic_bundle(req,retrieved_at=NOW-timedelta(seconds=61)),
            synthetic_bundle(req,provider="fixture_map",source_type="structured_api",value=StatusValue(status="open")))
    elif case_id in {"provider_error","provider_timeout","empty_provider"}:
        providers=[FixtureProvider(error=RuntimeError("SECRET must not escape") if case_id=="provider_error"
            else ProviderUnavailable("provider_timeout") if case_id=="provider_timeout" else None)]
    elif case_id=="unsupported_ticket":
        req=FactRequirement(fact_type="place.ticket_availability",subject=place())
    elif case_id.startswith("route_"):
        req=FactRequirement(fact_type="route.eta" if case_id=="route_eta_unsupported" else "route.duration",subject=route())
        async def gateway(subject):
            return (2400,32,"RoamSync Estimate" if case_id=="route_estimate_rejected" else "AMap Route 2.0",
                    case_id=="route_estimate_rejected",[],[])
        providers=[AMapRouteAdapter(freshness,gateway=gateway,clock=lambda:NOW)]
    elif case_id.startswith("poi_"):
        kind={"poi_identity":FactType.PLACE_IDENTITY,"poi_location":FactType.PLACE_LOCATION,"poi_native_category":FactType.PLACE_CATEGORY}[case_id]
        req=FactRequirement(fact_type=kind,subject=place())
        async def gateway(name,destination): return [poi_fixture()]
        providers=[AMapPoiAdapter(freshness,gateway=gateway,clock=lambda:NOW)]
    elif case_id.startswith("weather_"):
        req=FactRequirement(fact_type="weather.current" if case_id=="weather_current_unsupported" else "weather.forecast",
            subject=destination(),time_scope=TimeScope(start=NOW+timedelta(hours=6)))
        async def gateway(subject,time_scope,now):
            return weather_fixture(retrieved_at=NOW-timedelta(seconds=301) if case_id=="weather_stale_forecast" else NOW)
        providers=[WeatherForecastAdapter(freshness,gateway=gateway)]
    elif case_id.startswith("canonical_"):
        activity=case_id=="canonical_activity_status"
        req=FactRequirement(fact_type="execution.activity_status" if activity else "navigation.eta",
            subject=canonical_subject("activity_execution" if activity else "navigation_session"))
        reader=FixtureExecutionReader(observed_at=NOW-timedelta(seconds=11) if case_id=="canonical_navigation_stale" else NOW,
            simulation=case_id=="canonical_simulation_excluded")
        providers=[ExecutionFactAdapter(freshness,reader=reader)]
    else:
        raise ValueError("unknown benchmark case")
    result=await TravelFactService(repository,freshness,authority,providers,clock=lambda:NOW).resolve_fact(req)
    if req.fact_type.value.startswith(("execution.","navigation.")):
        assert not (await repository.get(req)).facts
    return result


async def benchmark():
    path=Path(__file__).with_name("cases.json"); cases=json.loads(path.read_text(encoding="utf-8"))
    rows=[]
    for case in cases:
        result=await scenario(case["id"])
        actual_value=result.value.model_dump(mode="json") if result.value else None
        refs={e.id for e in result.evidence}
        referenced={e.id for e in result.selected_evidence+result.conflicting_evidence}
        for fact in tuple(r.fact for r in result.rejected_candidates)+result.conflicting_facts+((result.selected_fact,) if result.selected_fact else ()):
            referenced.update(fact.evidence_refs)
        checks={
            "freshness_correctness":result.freshness_status==case["freshness"] and result.usable_as_current==case["current"],
            "provenance_preservation":len(refs)==case["evidence"] and referenced<=refs
                and all(e.retrieved_at and e.payload_trust=="untrusted_data_no_tool_authority" for e in result.evidence),
            "resolution_correctness":result.resolution_status==case["status"] and (actual_value is None if case["value"] is None
                else actual_value is not None and subset(case["value"],actual_value)),
            "conflict_preservation":len(result.conflicting_facts)==case["conflicts"] and (not case["conflicts"] or bool(result.conflicting_evidence)),
        }
        if case["value"] is None:
            checks["unavailable_honesty"]=result.value is None and not result.usable_as_current and len(result.provider_failures)==case.get("failures",0)
        rows.append({"id":case["id"],"status":result.resolution_status,"freshness":result.freshness_status,
            "usable_as_current":result.usable_as_current,"value":actual_value,"evidence_ids":sorted(refs),
            "conflict_count":len(result.conflicting_facts),"provider_failures":result.provider_failures,"checks":checks})
    metrics={name:{"passed":sum(row["checks"].get(name) is True for row in rows),
        "total":sum(name in row["checks"] for row in rows)} for name in rows[0]["checks"]|{"unavailable_honesty":True}}
    return {"benchmark":"travel_fact_resolution_v1","fixture_time":NOW.isoformat(),"measured_at":datetime.now(UTC).isoformat(),
        "fixture_sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"case_count":len(rows),
        "passed_cases":sum(all(row["checks"].values()) for row in rows),"metrics":metrics,"cases":rows,
        "limitations":["Synthetic offline inputs; no live API validation","Explicit TEST TTLs are not production SLAs",
                        "Deterministic fact resolution, not Agent answer quality","SQL read-only evidence belongs to PostgreSQL tests"]}


def main():
    parser=argparse.ArgumentParser(); parser.add_argument("--output",type=Path); args=parser.parse_args()
    report=asyncio.run(benchmark()); rendered=json.dumps(report,ensure_ascii=False,indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True); args.output.write_text(rendered+"\n",encoding="utf-8")
    print(rendered)
    return 0 if report["passed_cases"]==report["case_count"] else 1


if __name__=="__main__":
    raise SystemExit(main())
