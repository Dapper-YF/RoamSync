import asyncio
import json
import uuid
from types import SimpleNamespace

import pytest

from app.openai_planner import OpenAIResponsesPlanner
from app.planner_references import PlannerReferenceCodec
from app.planning_errors import PlannerProviderError
from test_openai_planner import _settings, _state


def test_reference_roundtrip_covers_ledger_memory_schema_and_composite_refs():
    place, activity, memory = (str(uuid.uuid4()) for _ in range(3))
    prompt = {"allowed_places": [{"place_candidate_id": place}],
              "activity_decision_semantics": [{"activity_id": activity}],
              "previous_user_feedback": [{"source_revision_id": memory, "reason_code": "too_rushed"}],
              "previous_plan": {"candidate_id": "candidate:1:" + place}}
    codec = PlannerReferenceCodec(prompt)
    encoded = codec.encode(prompt)
    assert codec.decode(encoded) == prompt
    assert place not in json.dumps(encoded)
    schema = {"type": "string", "format": "uuid", "enum": [place]}
    assert codec.encode(schema, schema=True) == {"type": "string", "enum": [codec.encode_map[place]]}
    assert codec.decode("ref_9999") == "ref_9999"
    assert codec.decode("ref_00001") == "ref_00001"


class GlmCompletions:
    def __init__(self, error=None, always_invalid=False):
        self.error = error
        self.always_invalid = always_invalid
        self.requests = []

    async def create(self, **kwargs):
        self.requests.append(kwargs)
        prompt = json.loads(kwargs["messages"][1]["content"])
        reference = prompt["new_place_candidates"][0]["candidate_ref"]
        payload = {"activities": [{"day_date": "2026-11-02", "source": "candidate", "candidate_ref": reference,
                    "planned_start_time": "10:00:00", "duration_minutes": 90,
                    "transport_mode_to_here": "transit", "reason": "符合当前旅行的历史文化兴趣"}],
                   "explanation": "保留固定活动，为游览留出停留空间。", "decision_ledger": []}
        bad = self.always_invalid or len(self.requests) == 1
        if self.error == "reference" and bad:
            payload["activities"][0]["candidate_ref"] = "ref_9999"
        if self.error == "protected" and bad:
            payload["activities"][0]["candidate_ref"] = prompt["protected_activities"][0]["activity_ref"]
        content = '{"activities":[' if self.error == "json" and bad else json.dumps(payload)
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content=content))],
                               usage=SimpleNamespace(total_tokens=12), model="glm-5.3-flash")


@pytest.mark.parametrize("error", [None, "reference", "json"])
def test_glm_exact_references_and_bounded_output_repair(error):
    state, candidate_id, _ = _state()
    completions = GlmCompletions(error)
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    settings = _settings(planner_provider="glm", planner_model="glm-5.3-flash", planner_reasoning_effort="max")
    result = asyncio.run(OpenAIResponsesPlanner(settings, client=client).generate(state))
    assert str(result.snapshot.activities[0].place_candidate_id) == candidate_id
    assert result.snapshot.activities[0].estimated_cost_fen == 5000
    assert len(completions.requests) == (1 if error is None else 2)
    assert result.token_usage == 12 * len(completions.requests)
    if error:
        retry = json.loads(completions.requests[1]["messages"][1]["content"])
        assert retry["output_error"] and retry["previous_invalid_output"]


@pytest.mark.parametrize("error", ["reference", "protected"])
def test_unissued_or_protected_reference_is_never_authorized_and_second_failure_stops(error):
    state, _, _ = _state()
    completions = GlmCompletions(error, always_invalid=True)
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    with pytest.raises(PlannerProviderError) as failure:
        asyncio.run(OpenAIResponsesPlanner(_settings(planner_provider="glm"), client=client).generate(state))
    assert failure.value.code == "planner_invalid_output"
    assert len(completions.requests) == 2
