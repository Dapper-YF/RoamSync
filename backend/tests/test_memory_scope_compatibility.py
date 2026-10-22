"""A's integration counterexamples for persisted pre-B scope semantics."""
from uuid import uuid4

import pytest

from app.assistant_context import ContextEnvelope
from app.assistant_memory import MemoryUpdate, apply_memory


@pytest.mark.parametrize("collection", ["preferences", "requirements"])
def test_legacy_temporary_personal_label_does_not_gain_cross_journey_lifetime(collection):
    memory = {"version": 1, "epoch": "legacy", "slots": {}, "preferences": [], "requirements": []}
    memory[collection] = [{"value": "这趟带父母，少走路", "scope": "personal",
                           "source_quote": "这趟带父母，少走路", "message_id": str(uuid4())}]
    envelope, _, _ = apply_memory(ContextEnvelope(conversation_memory=memory), [], "另一趟旅行，我自己去", uuid4())
    assert not envelope.conversation_memory[collection]


def test_new_explicit_personal_scope_remains_distinct_from_legacy_labels():
    envelope, _, _ = apply_memory(ContextEnvelope(), [], "我一直吃素", uuid4(), [
        MemoryUpdate(field="preferences", operation="add", value="吃素", source_quote="我一直吃素", scope="personal")])
    envelope.conversation_memory["preferences"].append({"value": "这趟带父母", "scope": "personal",
        "source_quote": "这趟带父母", "message_id": str(uuid4())})
    envelope, _, _ = apply_memory(envelope, [], "另一趟旅行，我自己去", uuid4())
    assert [item["value"] for item in envelope.conversation_memory["preferences"]] == ["吃素"]
