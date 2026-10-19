"""Provider-independent semantic contract and exact server-owned identity binding."""
import json
import re
from datetime import date, time
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError
from app.planner_references import PlannerReferenceCodec
from app.schemas import CandidateActivity, CandidatePlanSnapshot, DecisionLedgerEntry


class ExistingActivityDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: Literal["existing"]
    activity_ref: str
    day_date: date
    planned_start_time: time
    duration_minutes: int = Field(ge=15, le=480)
    transport_mode_to_here: Literal["walk", "transit", "driving"]
    reason: str = Field(max_length=500)


class NewActivityDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: Literal["candidate"]
    candidate_ref: str
    day_date: date
    planned_start_time: time
    duration_minutes: int = Field(ge=15, le=480)
    transport_mode_to_here: Literal["walk", "transit", "driving"]
    reason: str = Field(max_length=500)


class SemanticPlannerOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    activities: list[Annotated[ExistingActivityDecision | NewActivityDecision, Field(discriminator="source")]] = Field(max_length=100)
    explanation: str = Field(max_length=2000)


class InvalidPlannerReference(ValueError):
    pass


class PlannerEntityBindings:
    def __init__(self, prompt, allowed):
        self.existing = {}
        self.candidates = {}
        self.codec = PlannerReferenceCodec(prompt)
        # Activity refs follow formal itinerary order, independent of candidate ranking.
        formal = prompt.get("current_editable_activities", []) + prompt.get("protected_activities", []) + prompt.get("out_of_scope_activities", [])
        for index, item in enumerate(formal, 1):
            ref = f"activity_{index}"
            self.codec.encode_map[item["activity_id"]] = ref
            place = next((p for p in allowed.values() if str(p.replaces_activity_id) == item["activity_id"]), None)
            if place is not None:
                self.existing[ref] = place
        for index, item in enumerate(prompt.get("allowed_places", []), 1):
            place = next((p for p in allowed.values() if str(p.id) == item["place_candidate_id"]), None)
            if place is not None and place.replaces_activity_id is None:
                ref = f"candidate_{len(self.candidates) + 1}"
                self.candidates[ref] = place
                self.codec.encode_map[str(place.id)] = ref
        self.codec.decode_map = {ref: identity for identity, ref in self.codec.encode_map.items()}

    def prompt(self, raw):
        prompt = dict(raw)
        items = []
        for item in prompt.get("arrangement_items", []):
            clean = {k: item.get(k) for k in ("kind", "label", "day_date", "start", "end")}
            clean["candidate_ref"] = next((ref for ref, place in self.candidates.items() if str(place.id) == str(item.get("place_id"))), None)
            clean["activity_ref"] = next((ref for ref, place in self.existing.items() if str(place.replaces_activity_id) == str(item.get("activity_id"))), None)
            clean["place_status"] = "resolved" if item.get("place_id") else "unresolved_user_name"
            items.append(clean)
        prompt["arrangement_items"] = items
        # Facts remain in provenance/debug state; the model receives each partition once.
        for key in ("planning_goals", "formal_route_facts", "current_formal_plan", "user_preferences", "allowed_ledger_references", "activity_decision_semantics"):
            prompt.pop(key, None)
        prompt["existing_activities"] = [{k: v for k, v in item.items() if k != "place_candidate_id"}
                                         for item in prompt.pop("current_editable_activities", [])]
        prompt["new_place_candidates"] = [item for item in prompt.pop("allowed_places", [])
                                           if item["place_candidate_id"] in {str(p.id) for p in self.candidates.values()}]
        for key in ("protected_activities", "out_of_scope_activities"):
            prompt[key] = [{k: v for k, v in item.items() if k != "place_candidate_id"} for item in prompt[key]]
        # Bound memory volume; stored rejection facts and isolation remain unchanged.
        prompt["previous_user_feedback"] = [{k: item[k] for k in (
            "source_revision_id", "target_day", "rejection_reason_code", "rejection_reason_text", "previous_candidate_summary"
        ) if k in item} for item in prompt.get("previous_user_feedback", [])[:3]]
        for memory in prompt["previous_user_feedback"]:
            summary = memory.get("previous_candidate_summary", {})
            memory["previous_candidate_summary"] = {k: v[:10] if isinstance(v, list) else v for k, v in summary.items()}
        if "previous_plan" in prompt:
            previous = dict(prompt["previous_plan"])
            choices = {str(place.id): ("existing", ref) for ref, place in self.existing.items()}
            choices.update({str(place.id): ("candidate", ref) for ref, place in self.candidates.items()})
            route_refs = {}
            activities = []
            for item in previous.get("activities", []):
                choice = choices.get(item.get("place_candidate_id"))
                if choice is None:
                    # An unavailable prior choice is not re-authorized in a repair.
                    continue
                source, ref = choice
                if item.get("candidate_id"):
                    route_refs[item["candidate_id"]] = ref
                decision = {k: v for k, v in item.items() if k not in {"candidate_id", "place_candidate_id"}}
                decision.update(source=source)
                decision["activity_ref" if source == "existing" else "candidate_ref"] = ref
                activities.append(decision)
            previous["activities"] = activities
            previous["route_legs"] = [{**leg,
                "from_activity_ref": route_refs.get(leg["from_activity_ref"], leg["from_activity_ref"]),
                "to_activity_ref": route_refs.get(leg["to_activity_ref"], leg["to_activity_ref"])}
                for leg in previous.get("route_legs", [])]
            prompt["previous_plan"] = previous
        encoded = self.codec.encode(prompt)
        def rename(value):
            if isinstance(value, dict):
                return {k.replace("activity_ids", "activity_refs").replace("activity_id", "activity_ref").replace("place_candidate_id", "candidate_ref"): rename(v) for k, v in value.items()}
            if isinstance(value, list):
                return [rename(v) for v in value]
            return value
        encoded = rename(encoded)
        encoded["allowed_activity_refs"] = list(self.existing)
        encoded["allowed_candidate_refs"] = list(self.candidates)
        return encoded

    def schema(self, dates):
        schema = SemanticPlannerOutput.model_json_schema()
        for name, field, refs in (("ExistingActivityDecision", "activity_ref", self.existing), ("NewActivityDecision", "candidate_ref", self.candidates)):
            props = schema["$defs"][name]["properties"]
            props[field]["enum"] = list(refs)
            props["day_date"]["enum"] = sorted(d.isoformat() for d in dates)
        # An empty domain must not create an invalid empty JSON Schema enum.
        variants = []
        if self.existing:
            variants.append({"$ref": "#/$defs/ExistingActivityDecision"})
        if self.candidates:
            variants.append({"$ref": "#/$defs/NewActivityDecision"})
        schema["properties"]["activities"]["items"] = {"anyOf": variants} if variants else {"not": {}}
        if not variants:
            schema["properties"]["activities"]["maxItems"] = 0
        for name in ("ExistingActivityDecision", "NewActivityDecision"):
            if not schema["$defs"][name]["properties"].get("activity_ref", schema["$defs"][name]["properties"].get("candidate_ref"))["enum"]:
                schema["$defs"].pop(name)
        return schema


def parse_semantic_planner_output(value, bindings):
    from app.openai_planner import normalize_structured_json
    payload = json.loads(normalize_structured_json(value))
    if not isinstance(payload, dict):
        raise ValueError("planner output must be an object")
    payload = dict(payload)
    ledger = payload.pop("decision_ledger", None)
    errors = []
    parsed_ledger = None
    if ledger is not None:
        try:
            parsed_ledger = TypeAdapter(list[DecisionLedgerEntry]).validate_python(bindings.codec.decode(ledger))
            if len(parsed_ledger) > 150:
                raise ValueError("ledger limit")
        except (ValidationError, ValueError):
            parsed_ledger = None
            errors.append("decision_ledger_output_invalid")
    if isinstance(payload.get("explanation"), str) and re.search(r"\d+\s*(?:元|分钟|公里|km|米)", payload["explanation"], re.IGNORECASE):
        errors.append("decision_explanation_unverified")
    draft = SemanticPlannerOutput.model_validate(payload)
    return draft, parsed_ledger, errors


def resolve_planner_activity_references(draft, bindings, allowed_dates, *, ledger=None, errors=None):
    activities = []
    used = set()
    for index, selection in enumerate(draft.activities, 1):
        refs = bindings.existing if selection.source == "existing" else bindings.candidates
        ref = selection.activity_ref if selection.source == "existing" else selection.candidate_ref
        place = refs.get(ref)
        if place is None:
            raise InvalidPlannerReference(f"Invalid {selection.source} ref: {ref}. Allowed: {', '.join(refs)}")
        if selection.day_date not in allowed_dates:
            raise ValueError("day_date outside allowed dates")
        if place.id in used:
            raise ValueError("duplicate place selection")
        used.add(place.id)
        activities.append(CandidateActivity(
            candidate_id=f"candidate:{index}:{place.id}", day_date=selection.day_date,
            place_candidate_id=place.id, replaces_activity_id=place.replaces_activity_id,
            planned_start_time=selection.planned_start_time, duration_minutes=selection.duration_minutes,
            transport_mode_to_here=selection.transport_mode_to_here, reason=selection.reason.strip(),
            estimated_cost_fen=place.estimated_cost_fen, source_ids=[place.source_id], locked=False,
        ))
    return CandidatePlanSnapshot(activities=activities, explanation=draft.explanation, decision_ledger=ledger, provenance_parse_errors=errors or [])
