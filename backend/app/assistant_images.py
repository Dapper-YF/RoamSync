"""Optional answer illustrations, separate from factual web research and writes."""
import asyncio
import re

from app.assistant_reliability import active_turn, bounded_call
from app.assistant_stream import emit
from app.assistant_search import project_search
from app.external_facts import search_tavily


def _visual_clauses(message):
    return [part for part in re.split(r'[，,。；;!?！？\n]', message)
        if re.search(r'图片|照片|配图|看看.{0,10}(?:样子|外观)', part)]


def _operation_limit(clause):
    return bool(re.search(r'(?:不用|不要|无需|别|不必)(?:再|先)?(?:生成|制作|保存|下载)', clause))


def _display_denied(clause, subject=''):
    text = clause.replace(subject, '') if subject else clause
    return bool(re.search(r'(?:不用|不要|无需|别|不必)(?:再|先|任何)?(?:展示|显示|提供|看)?(?:的)?(?:实景)?(?:配图|图片|照片|图)', text)
        or re.search(r'(?:图片|照片|图)(?:先|暂时)?(?:不用|不要|别)(?:再)?(?:展示|显示|看)', text))


def image_requested(message):
    return any(not _operation_limit(clause) and not _display_denied(clause)
        for clause in _visual_clauses(message))


def requested_visual_subjects(names, message):
    """Narrow existing subjects; never introduce a name or a place identity."""
    clauses = [part for part in _visual_clauses(message) if not _operation_limit(part)]
    display = {name: re.split(r'[（(]', name)[0] for name in names}
    named = {name for name, label in display.items() for part in clauses
        if label in part and not _display_denied(part, label)}
    broad = any(not any(label in part for label in display.values())
        and not _display_denied(part) for part in clauses)
    return [name for name, label in display.items() if (broad or name in named)
        and not any(label in part and _display_denied(part, label) for part in clauses)]


def subjects_for_answer(bundle, message, envelope):
    preference = envelope.conversation_memory.get("slots", {}).get("images", {}).get("value", "")
    if any(_display_denied(clause) for clause in _visual_clauses(message)) or _display_denied(str(preference)):
        return []
    answer = bundle.get("assistant", "")
    subjects = (bundle.get("companion_result") or {}).get("visual_subjects", [])
    requested = image_requested(message)
    # Explicit visuals are an independent read goal. Aggregated text tasks can
    # omit visual_subjects; negative planning clauses must not cancel this goal.
    if requested or (not subjects and re.search(r"介绍|样子|外观|建筑|美食|景色|风景|图片|照片|看看", message)
        and not re.search(r"路线|怎么走|天气|营业|地址|预约|来源|规划|安排", message)):
        cards = bundle.get("place_cards", [])
        if cards:
            subjects = [{"subject": card["place"]["name"], "kind": "attraction"}
                for card in cards if card.get("place", {}).get("name") and card['place']['name'] in answer]
    if requested:
        allowed = requested_visual_subjects([item['subject'] for item in subjects], message)
        subjects = [item for item in subjects if item['subject'] in allowed]
    result = []
    for item in subjects:
        subject = item.get("subject", "")
        if item.get("kind") not in {"food", "attraction", "architecture"}:
            continue
        # A selector cannot smuggle a URL, instruction or a subject omitted by
        # final validation into a provider query. No current-user text is copied.
        if (subject not in answer or not re.fullmatch(r"[\w·（）()\-\s]{2,80}", subject)
            or subject in [i["subject"] for i in result]):
            continue
        result.append(item)
    return result[:2]


async def enrich_images(settings, bundle, message, envelope, *, search=None):
    subjects = subjects_for_answer(bundle, message, envelope)
    if not subjects:
        return
    turn = active_turn.get()
    seconds = min(18, turn.remaining() - .5) if turn else 18
    if seconds <= .1:
        return
    emit("status", message="正在查找相关图片…")
    tools = bundle.setdefault("read_tools", {})
    requested = image_requested(message)
    # Image failures must never alter the text, answer status or citations.
    async def lookup(item):
        subject = item["subject"]
        city = envelope.browsing_city or ""
        query = f"{city} {subject} 图片".strip()
        async def request():
            options = settings.model_copy(update={"search_timeout_seconds": min(16, settings.search_timeout_seconds)})
            fact = await (search or search_tavily)(options, query=query, max_results=2, include_images=True, retry_attempts=1)
            projected = project_search(fact, subject + "的图片")
            return [{**image, "usage_basis": "search_reference", "illustration_kind": item["kind"]}
                for image in projected["images"][:1]]
        try:
            return await bounded_call(request, stage="images", limit=seconds)
        except Exception:
            return []
    try:
        batches = await asyncio.gather(*(lookup(item) for item in subjects))
        images = list({image["url"]: image for batch in batches for image in batch}.values())[:3]
        tools["visuals"] = {"status": "available" if images else "unavailable", "images": images,
            "requested": requested,
            "semantics": "optional_topic_illustrations_not_factual_evidence"}
    except Exception:
        # A projection/provider failure is optional even after successful prose.
        tools["visuals"] = {"status": "unavailable", "images": [], "requested": requested}
