import asyncio
import json
from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from app.companion_contracts import CompanionContext
from app.companion_information import determine_information_need
from app.travel_goal_router import route_travel_goal
from evals.companion_blind_review import export
from evals.companion_provider_smoke import failure_details, public_endpoint


@pytest.mark.parametrize("destination",["南京","苏州"])
def test_explicit_cultural_planning_destination_overrides_comparison_history(destination):
    from app.companion_state import build_planning_brief, destination_from_text
    other = "苏州" if destination == "南京" else "南京"
    history=[{"id":"pref","user":"我喜欢安静的街巷和历史文化，不喜欢排队。"},
        {"id":"compare","user":f"{other}和{destination}哪个更适合慢节奏？"}]
    text=f"帮我规划{destination}三天行程，优先历史文化和安静街巷。"
    brief=build_planning_brief("s","plan",text,route_travel_goal(text),history)
    assert brief.destination==destination and brief.duration_days==3
    assert brief.confirmed_preferences[0].source_turn_id=="pref"
    assert destination_from_text(f"{destination}有哪些历史文化特色？") is None
    denied=f"先不要帮我规划{destination}三天历史文化行程。"
    assert build_planning_brief("s","denied",denied,route_travel_goal(denied),history) is None


def test_diagnostics_remove_credentials_and_sensitive_error_bodies():
    class UpstreamError(Exception):
        status_code = 403
        body = {"error": {"code": "authentication_error", "message": "private-response-secret"}}
    outer = ValueError("private-user-message")
    outer.__cause__ = UpstreamError("private-key")
    details = failure_details(outer)
    assert details["exception_chain"][1] == {"type": "UpstreamError", "http_status": 403,
        "provider_error_code": "authentication_error"}
    assert "private" not in json.dumps(details)
    assert public_endpoint("https://user:secret@example.com:443/api?key=secret") == {
        "scheme":"https", "host":"example.com", "port":443, "path":"/api"}


def test_filtered_incomplete_response_is_recorded_without_format_retry(monkeypatch):
    import app.companion_provider as module
    class Client:
        closed = False
        async def close(self):
            self.closed = True
    client = Client()
    monkeypatch.setattr(module,"get_settings",lambda:SimpleNamespace(
        planner_api_key=SecretStr("test"),planner_model="test",planner_provider="glm"))
    monkeypatch.setattr(module,"build_model_client",lambda settings:client)
    async def filtered(*args,**kwargs):
        return SimpleNamespace(status="incomplete",finish_reason="sensitive",output_text="",usage=None)
    monkeypatch.setattr(module,"create_model_response",filtered)
    provider = module.ModelCompanionProvider()
    context = CompanionContext(current_message="一个人旅游有什么建议？",
        travel_goal=route_travel_goal("一个人旅游有什么建议？"))
    with pytest.raises(module.CompanionProviderError) as caught:
        asyncio.run(provider.generate(context,determine_information_need(context,[])))
    assert caught.value.code == "planner_incomplete_output"
    assert len(provider.observations) == 1 and client.closed
    assert provider.observations[0]["finish_reason"] == "sensitive"
    assert provider.observations[0]["usage"] is None


def test_blind_packet_omits_mode_and_debug_and_keeps_original_answer(tmp_path):
    path = tmp_path/"real.json"
    path.write_text(json.dumps({"rows":[{"mode":"C","case_id":"x","input":"hello","history":[],
        "output":{"response_text":"answer","knowledge_evidence":[{"evidence_ref":"unused", "text":"debug"}]}},
        {"mode":"A","case_id":"error","input":"hello","output":None,"error":"failure"}]}),encoding="utf-8")
    export([path],tmp_path/"blind")
    packet=json.loads((tmp_path/"blind/blind_packet.json").read_text(encoding="utf-8"))
    assert len(packet)==1 and packet[0]["answer"]=="answer"
    assert "mode" not in packet[0] and "debug" not in json.dumps(packet)
    key=json.loads((tmp_path/"blind/blind_key.json").read_text(encoding="utf-8"))
    assert key[0]["mode"]=="C" and key[0]["row"]==0
