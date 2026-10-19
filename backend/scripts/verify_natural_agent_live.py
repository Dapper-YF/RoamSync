"""Synthetic live API/model/map probe. Only the isolated loopback service."""
from datetime import datetime, UTC
import json
from pathlib import Path
from uuid import uuid4

import httpx

OUT = Path(__file__).resolve().parents[2] / "docs/evidence/natural-assistant"
run_id = str(uuid4())
report = {"run_id": run_id, "started_at": datetime.now(UTC).isoformat(), "kind": "real API/model/map; synthetic user; isolated DB", "steps": []}
path = OUT / f"live-{run_id}.json"


def record(step, **data):
    report["steps"].append({"step": step, **data})
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(step, data.get("status", "recorded"), flush=True)


try:
    with httpx.Client(base_url="http://127.0.0.1:18019", timeout=160, trust_env=False) as c:
        before = c.get("/api/v1/trips").json()
        created = c.post("/api/v1/assistant/sessions", json={})
        created.raise_for_status()
        session = created.json()
        context = {"version": "assistant-context-v1", "topic_id": f"live-{run_id}", "surface": "assistant", "prefer_flexible": True}
        messages = [
            "第一次去南京，想了解南京博物院和玄武湖的体验有什么区别，先只聊聊，不创建旅行。",
            "我想看历史展览，南京博物院确定想去但时间未定；玄武湖有时间再去就好。现在先讨论。",
            "我决定2026-11-07到2026-11-08去南京两天。周日总统府14:00-15:00已经预约；周六15:00-16:00明确留白。保留南京博物院但暂不排时间，玄武湖还是备选。请形成允许留白的旅行安排建议，别把两天填满。",
        ]
        for index, message in enumerate(messages):
            response = c.post(f"/api/v1/assistant/sessions/{session['id']}/messages", json={"message": message, "message_id": str(uuid4()), "context": context})
            data = response.json()
            record(f"message-{index+1}", status=response.status_code, body=data)
            response.raise_for_status()
            assert data["trip_id"] is None
            if index < 2:
                assert not data["pending_action"] and c.get("/api/v1/trips").json() == before
        action = data["pending_action"]
        assert action and action.get("flexible"), "no usable flexible preview"
        context["preview_action_id"] = action["id"]
        adopted = c.post(f"/api/v1/assistant/sessions/{session['id']}/messages", json={"message": "就按这份来", "message_id": str(uuid4()), "context": context})
        record("adopt", status=adopted.status_code, body=adopted.json())
        adopted.raise_for_status()
        tid = adopted.json()["trip_id"]
        assert tid and adopted.json()["latest_run_id"] is None
        state = c.get(f"/api/v1/trips/{tid}/arrangement-items").json()
        record("saved-readback", status=200, body=state)
        assert any(i["kind"] == "free_window" for i in state["items"])
        assert any("玄武湖" in i["label"] and i["kind"] == "optional" for i in state["items"])
        assert any("博物院" in i["label"] and i["activity_id"] is None for i in state["items"])
        assert any(a["schedule_locked"] and a["scheduled_time"] == "14:00:00" for d in state["days"] for a in d["activities"])
        report["result"] = "PASS bounded live creation chain; no dynamic Graph/browser claim"
except Exception as exc:
    report["result"] = "FAIL"
    report["failure"] = {"type": type(exc).__name__, "message": str(exc)[:1000]}
finally:
    report["finished_at"] = datetime.now(UTC).isoformat()
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(report["result"], path, flush=True)
if report["result"] == "FAIL":
    raise SystemExit(1)
