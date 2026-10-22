"""Decision help from observed inputs, separate from claims about unknown venues."""
import math
import re
from decimal import Decimal, InvalidOperation


def active_condition_text(memory):
    """Only effective values, never old source quotes or withdrawal records."""
    memory = memory or {}
    return " ".join(str(item.get("value", "")) for item in [
        *memory.get("slots", {}).values(), *memory.get("preferences", []), *memory.get("requirements", [])])


def research_decision_support(envelope, candidates, category):
    """Deterministic arithmetic over compatible reference costs, never a bill.

    A total/daily/hotel budget cannot be compared with restaurant per-person
    reference spending. Unspecified units stay unknown instead of being guessed.
    No menu, accessibility or internal-walking facts are inferred from a POI.
    """
    from app.assistant_memory import memory_prompt
    conditions = memory_prompt(envelope)
    entry = conditions["slots"].get("budget", {})
    text = str(entry.get("source_quote", ""))
    budget = None
    match = re.search(r"(?:人均|每人)\s*(?:预算|餐费|消费)?\s*(?:不超过|最多|上限(?:为)?|控制在|约|大约|为|是|在)?\s*(\d+(?:\.\d{1,2})?)\s*元", text)
    if (category == "food" and match and not re.search(r"每天|每日|一天|全程|总预算|总共|合计|住宿|酒店|门票|交通", text)):
        amount = Decimal(match[1])
        if amount > 0:
            budget = {"amount_yuan": float(amount), "unit": "per_person_meal",
                      "source_quote": text, "message_id": entry.get("message_id")}
    items = []
    for index, place in enumerate(candidates, 1):
        cost = place.reference_cost_yuan
        relation, difference = "not_comparable", None
        if budget:
            relation = "unknown"
            if cost is not None:
                try:
                    difference = Decimal(str(cost)) - Decimal(str(budget["amount_yuan"]))
                    if difference.is_finite():
                        relation = "above_reference_limit" if difference > 0 else "within_reference_limit"
                        difference = float(difference)
                    else:
                        difference = None
                except InvalidOperation:
                    difference = None
        items.append({"place_id": str(place.place_id), "name": place.name,
                      "reference_source_id": f"poi_{index}", "citation_index": index,
                      "reference_cost_yuan": cost, "budget_relation": relation, "difference_yuan": difference,
                      "diet_suitability": "unknown", "on_site_walking": "unknown"})
    return {"conditions": conditions, "budget": budget, "candidates": items,
            "semantics": "reference_cost_comparison_not_actual_bill_or_venue_suitability"}


def render_research_decision_support(support, category):
    """A useful decision remains possible when generative prose is unavailable."""
    parts = []
    budget = support["budget"]
    if budget:
        limit = f"{budget['amount_yuan']:g}"
        comparisons = []
        for item in support["candidates"]:
            relation = item["budget_relation"]
            name = f"{item['name']} [{item['citation_index']}]"
            if relation == "above_reference_limit":
                comparisons.append(f"{name}的高德参考人均高出{limit}元上限{item['difference_yuan']:g}元，按花费先降低优先级")
            elif relation == "within_reference_limit":
                comparisons.append(f"{name}的参考人均比上限低{abs(item['difference_yuan']):g}元，可先核对菜单")
            else:
                comparisons.append(f"{name}缺少参考消费，无法判断预算是否合适")
        parts.append("；".join(comparisons) + "。参考人均不等于这顿实际账单。")
    conditions = active_condition_text(support["conditions"])
    if category == "food" and re.search(r"不吃|不能吃|吃不了|吃素|素食|过敏|忌口", conditions):
        dietary = [item["value"] for key in ("preferences", "requirements") for item in support["conditions"][key]
                   if re.search(r"不吃|不能吃|吃不了|吃素|素食|过敏|忌口", item["value"])]
        label = "、".join(dietary[:3])
        parts.append(f"饮食要求{('（' + label + '）') if label else ''}仍需逐家核对：目前的地点信息不能证明能提供符合你忌口的餐食，先确认食材、汤底和调料，再决定；参考消费低也不能证明适合。")
    return "\n\n".join(parts)


def research_options(candidates, sources, message=""):
    options=[]
    for index, place in enumerate(candidates,1):
        details=[]
        if place.address:
            details.append(place.address)
        if place.reference_cost_yuan is not None:
            details.append(f"高德参考消费约{place.reference_cost_yuan:g}元")
        if re.search(r"评分|评价|口碑",message) and place.rating is not None:
            details.append(f"高德参考评分{place.rating:g}")
        options.append(place.name + ("（" + "；".join(details) + "）" if details else "") + f" [{index}]")
    return "先保留这几个实际查到的选择：" + "；".join(options) + "。" if options else "这次没有取得足以辨认的地点。"


def practical_next_step(message, category, *, city="", memory=None):
    # These are choices/verification actions, never assertions that an amenity,
    # menu, low-effort path or commercial promise exists.
    conditions=active_condition_text(memory) + " " + message
    if re.search(r"累了|想休息|不想去|不出门",message) and not re.search(r"推荐|还有|替代|怎么",message):
        return "那就先休息，不必再加一处。"
    if category == "food":
        diet=bool(re.search(r"不吃辣|不能吃辣|清汤|忌口|素食|吃素|过敏",conditions))
        budget=bool(re.search(r"预算|人均|\d+元",conditions))
        if diet:
            return "我建议先按忌口筛选：点单前确认锅底、蘸料和配菜能否按要求处理，再看菜单总价决定；没核实前先作为候选。"
        if budget:
            return "比较花费时，把锅底、蘸料和必点菜一起算；高德参考消费只能帮助初筛，不能保证这顿账单。"
        return "如果只吃一顿，我建议先按你想吃的形式选，再核对菜单；地点信息还不能说明哪家味道更好。"
    if re.search(r"顺路|少走|省力|轻松|累|赶|多久|半天|小时",message):
        return "我建议先选最想看的一处，另一处保留备选；两点间路线和场所内部步行量确认后，再决定是否放在同一段时间。"
    return "可以先按兴趣选一处作为重点，其余保留备选；没有体验资料的部分暂不用于排名。"


def previous_reads(history):
    """Server-retrieved values only. Prior assistant prose never becomes evidence."""
    output=[]
    for turn in history[-12:]:
        tools=turn.get("read_tools") or {}
        route=tools.get("route") or {}
        if route.get("status")=="available" and isinstance(route.get("result"),dict):
            output.append({"kind":"route","message_id":turn.get("id"),"result":route["result"],
                "places":[{"name":c["place"]["name"],"city":c["place"]["city"]} for c in turn.get("place_cards",[])],
                "semantics":"previous_provider_estimate_not_live_or_on_site_walking"})
        for source in (tools.get("web_search") or {}).get("sources",[]):
            output.append({"kind":"source",**{k:source[k] for k in ("title","excerpt","read_level","retrieved_at","place_id") if k in source}})
    return output[-8:]


def walking_followup(reads):
    route=next((r for r in reversed(reads) if r["kind"]=="route"),None)
    if not route:
        return "我建议减少目的地数量，先选最想看的一处，另一处保留备选。还没有实际路线和场所内部步行信息，不能据此保证轻松或顺路。"
    value=route["result"]
    if value.get("is_estimated_fallback") or not isinstance(value.get("duration_seconds"),(int,float)):
        return "上次的路线还不足以判断步行负担。我建议先只选一处，确认实际交通与场所内部动线后再加第二处。"
    minutes=math.ceil(value["duration_seconds"]/60)
    mode="步行" if value.get("mode")=="walk" else "驾车"
    return (f"上次查到的两点间{mode}路线约{minutes}分钟；它没有计算场所内游览、等候和返程，也不能说明有无坡道或台阶。"
        + ("如果这段步行本身就超过你愿意走的量，我建议改查驾车，或把另一处留作备选。" if mode=="步行" else "我建议把有限体力留给最想看的一处，另一处先留作备选。"))
