"""Stable semantic conditions, excluding receipts and diagnostic timestamps."""
from app.draft_promotion.preparation import digest


def conditions_hash(envelope):
    from app.assistant_memory import memory_prompt
    memory = memory_prompt(envelope)
    records = [{key: record.get(key) for key in ("text", "key", "value", "scope", "strength")}
        for record in envelope.requirement_records if record.get("status") == "active"]
    values = {"slots": {key: value.get("value") for key, value in memory["slots"].items()},
        "preferences": sorted(str(item.get("value")) for item in memory["preferences"]),
        "requirements": sorted(str(item.get("value")) for item in memory["requirements"]),
        "withdrawn": sorted(memory.get("withdrawn", {})), "records": sorted(records, key=digest),
        "task_requirements": envelope.requirements.model_dump(mode="json") if envelope.requirements else None}
    return digest(values)


def row_conditions_hash(row, topic):
    from app.assistant_context import ContextEnvelope
    context = next((turn["context"] for turn in reversed(row.messages)
        if turn.get("context", {}).get("topic_id") == topic), {"topic_id": topic})
    return conditions_hash(ContextEnvelope.model_validate(context))
