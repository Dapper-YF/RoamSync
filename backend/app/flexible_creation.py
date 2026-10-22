"""Bounded creation preview fields; reuse the existing preview/confirmation."""
from datetime import date, time
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CreationChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["selected", "optional", "free_window", "appointment"]
    label: str = Field(min_length=1, max_length=160)
    origin: Literal["user_explicit", "ai_suggestion"] = "user_explicit"
    source_quote: str = Field(default="", max_length=600)
    day_date: date | None = None
    start: time | None = None
    end: time | None = None

    @model_validator(mode="after")
    def precision(self):
        if self.kind in {"appointment", "free_window"}:
            if self.day_date is None or self.start is None or self.end is None or self.start >= self.end:
                raise ValueError("时间范围需要完整且明确")
        elif self.start is not None or self.end is not None:
            raise ValueError("未排程选择不能擅自补时间")
        return self


def _compact(text):
    return re.sub(r"\s+", "", text).replace("：", ":")


def check_time_quote(choice, quote, start_date=None):
    # Deliberately bounded. Ambiguous/missing booking ranges require clarification.
    clocks = re.findall(r"(?<!\d)(\d{1,2}):(\d{2})(?!\d)", quote)
    expected = [(str(choice.start.hour), f"{choice.start.minute:02}"), (str(choice.end.hour), f"{choice.end.minute:02}")]
    clocks = [(str(int(h)), m) for h, m in clocks]
    if not all(pair in clocks for pair in expected):
        raise ValueError("请明确提供起止时间，例如14:00—15:00；不会猜测预约时长")
    tokens = [choice.day_date.isoformat(), f"{choice.day_date.month}月{choice.day_date.day}日",
        "周" + "一二三四五六日"[choice.day_date.weekday()], "星期" + "一二三四五六日"[choice.day_date.weekday()]]
    if start_date is not None:
        position = (choice.day_date - start_date).days + 1
        if 1 <= position <= 7:
            tokens += [f"第{position}天", "第" + "一二三四五六七"[position - 1] + "天"]
    if not any(token in quote for token in tokens):
        raise ValueError("时间范围还缺少与旅行日期一致的日期说明")


def recover_creation_quotes(decision, user_message):
    """Recover a malformed model quote from a unique literal current-user clause.

    Does not invent choices, resolve ambiguity, alter kind/time, or accept them.
    prepare_choices still validates identity, cancellation and precision.
    """
    clauses = [c.strip() for c in re.split(r"[，,。；;\n]", user_message) if c.strip()]
    choices = []
    for choice in decision.choices:
        if choice.kind not in {"selected", "optional"} or choice.origin != "user_explicit":
            choices.append(choice)
            continue
        label = re.split(r"[（(]|(?:已)?预约", choice.label, maxsplit=1)[0].strip()
        quote = _compact(choice.source_quote)
        if quote and quote in _compact(user_message) and _compact(label) in quote:
            choices.append(choice)
            continue
        matches = [c for c in clauses if _compact(label) in _compact(c)]
        unique = matches[0] if len(matches)==1 else ""
        name = re.escape(_compact(label))
        # Finite affirmative forms only. Do not interpret negation, questions or
        # arbitrary surrounding language as consent to an item.
        affirmative = re.fullmatch(
            r"(?:(?:保留|纳入|选定)"+name+r"|"+name+r"(?:确定想去|确定要去|想去|必去)|"
            +name+r"(?:还是|是|作为|只作|仅作)?(?:备选|可选))"
            r"(?:但?(?:暂不排时间|时间未定|尚未排时间|暂不定))?", _compact(unique))
        choices.append(choice.model_copy(update={"source_quote":unique})
                       if label and unique and len(unique)<=600 and affirmative else choice)
    return choices


async def prepare_choices(decision, city, user_text):
    from app.maps_service import search_amap_places
    source = _compact(user_text)
    prepared = []
    for choice in decision.choices:
        quote = _compact(choice.source_quote)
        # A display caption may include '(备选)' or '预约'. It is not a POI
        # identity; strip only these known captions before checking the quote.
        label = re.split(r"[（(]|(?:已)?预约", choice.label, maxsplit=1)[0].strip() if choice.kind != "free_window" else choice.label
        label = label or choice.label
        core_name = label.removeprefix(city["name"].rstrip("市")).strip() or label
        if choice.origin == "user_explicit" and (not quote or quote not in source or _compact(core_name) not in quote and choice.kind != "free_window"):
            raise ValueError(f"事项「{choice.label}」缺少含名称的逐字用户原话；请从user_source_text复制完整原句，不能概括或补写")
        if choice.day_date and not decision.start_date <= choice.day_date <= decision.end_date:
            raise ValueError("建议日期超出本次旅行")
        mentions = [part for part in re.split(r"[，,。；;\n]", user_text) if core_name in part]
        latest = mentions[-1] if mentions else ""
        if re.search(r"不去|取消|别安排|不想去", latest):
            raise ValueError("这次已撤销的地点不能从旧讨论中恢复，请核对建议")
        data = choice.model_dump(mode="json")
        data["label"] = label
        if choice.kind in {"selected", "optional"} and re.search(r"有时间|备选|不一定|看情况|可去可不去", quote or latest):
            data["kind"] = "optional"
        if choice.kind in {"selected", "optional"} and re.search(r"未定|不定|暂不排|没定", quote):
            data["day_date"] = None
        if choice.kind == "free_window" and choice.origin == "user_explicit":
            check_time_quote(choice, choice.source_quote.replace("：", ":"), decision.start_date)
        if choice.kind == "appointment":
            if choice.origin != "user_explicit" or not re.search(r"预约|订好|固定", quote) or re.search(r"取消|没订|未预约|不确定", quote):
                raise ValueError("固定预约必须来自用户明确提供的信息")
            check_time_quote(choice, choice.source_quote.replace("：", ":"), decision.start_date)
            if (choice.end.hour*60+choice.end.minute)-(choice.start.hour*60+choice.start.minute) < 5:
                raise ValueError("预约起止时间不足5分钟，请核对原始时间")
            places = await search_amap_places(label, city["name"])
            exact = [p for p in places if p.name in {label, core_name} or p.name.removeprefix(city["name"].rstrip("市")) == core_name]
            if len(exact) != 1:
                raise ValueError("预约地点尚未唯一核实，请从地点结果中明确选择；不会虚构地点")
            data["place_snapshot"] = exact[0].model_dump(mode="json")
        prepared.append(data)
    return prepared


async def adopt_choices(db, trip, action):
    from app.arrangement_service import ItemWrite, ItemSchedule, schedule_item, write_item
    from app.planner_repository import save_candidate_snapshot
    from app.database import DayPlan
    from app.schemas import PlaceSearchResultResponse
    from sqlalchemy import select
    from uuid import UUID, uuid5
    for index, choice in enumerate(action.get("choices", [])):
        data = CreationChoice.model_validate({k: v for k, v in choice.items() if k != "place_snapshot"})
        item_id = uuid5(UUID(action["id"]), f"choice:{index}")
        pid = None
        if data.kind == "appointment":
            place = await save_candidate_snapshot(db, trip.id, PlaceSearchResultResponse.model_validate(choice["place_snapshot"]))
            pid = place.id
        item = await write_item(db, trip.id, ItemWrite(id=item_id, expected_version=trip.version,
            kind="selected" if data.kind == "appointment" else data.kind, label=data.label,
            source_ref=f"preview:{action['id']}:{index}:{data.origin}", place_id=pid,
            day_date=data.day_date, start=data.start if data.kind == "free_window" else None,
            end=data.end if data.kind == "free_window" else None), commit=False)
        item.decision_ref = f"adopt-preview:{action['id']}"
        if data.kind == "appointment":
            day = await db.scalar(select(DayPlan.id).where(DayPlan.trip_id == trip.id, DayPlan.date == data.day_date))
            duration = (data.end.hour*60+data.end.minute)-(data.start.hour*60+data.start.minute)
            await schedule_item(db, trip.id, item.id, ItemSchedule(expected_version=trip.version,
                day_plan_id=day, scheduled_time=data.start, duration_minutes=duration, schedule_locked=True), commit=False)
