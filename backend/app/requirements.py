"""Explicit requirements in existing Topic/Draft/Trip JSON, never AI memory.

Records retain provenance and scoped overrides. A day override must not erase a
trip-wide requirement from other days. Unknown historical JSON fails closed.
"""
import re
from datetime import date, timedelta
from typing import Literal
from uuid import UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

_NS = UUID("e7e1d67e-7fa0-45c7-a47b-09667845af50")


class RequirementScope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["topic", "draft", "trip", "day", "activity", "global_preference"]
    topic_id: str | None = None
    draft_id: str | None = None
    trip_id: str | None = None
    city: str | None = None
    day_index: int | None = Field(default=None, ge=1, le=31)
    date: str | None = None
    activity_id: str | None = None

    @model_validator(mode="after")
    def bound_scope(self):
        if self.kind == "day" and not (self.date or self.day_index):
            raise ValueError("day requires date or relative day index")
        if self.kind == "activity" and not self.activity_id:
            raise ValueError("activity requires identity")
        if self.date:
            from datetime import date as calendar_date
            calendar_date.fromisoformat(self.date)
        if self.kind != "global_preference" and not (self.topic_id or self.draft_id or self.trip_id):
            raise ValueError("local requirements require owner scope")
        return self


class RequirementSource(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["user_explicit", "trip_preference"] = "user_explicit"
    ref: str


class EffectiveRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    text: str = Field(min_length=1, max_length=3000)
    key: str = "user_requirement"
    value: str | int | None = None
    source: RequirementSource
    scope: RequirementScope
    strength: Literal["hard", "soft"] = "soft"
    status: Literal["active", "revoked", "superseded"] = "active"
    supersedes: list[str] = Field(default_factory=list)


def valid_records(records):
    result = []
    for value in records or []:
        try:
            result.append(EffectiveRequirement.model_validate(value).model_dump(mode="json"))
        except (ValidationError, TypeError, ValueError):
            continue
    return result


def _matches(scope, *, trip_id=None, draft_id=None, topic_id=None, city=None,
             target_date=None, day_index=None, target_activity_ids=None, **_):
    if scope["kind"] == "global_preference":
        return True
    for key, expected in (("trip_id", trip_id), ("draft_id", draft_id), ("topic_id", topic_id)):
        if scope.get(key) and str(expected) != scope[key]:
            return False
    if scope.get("city") and (not city or scope["city"].removesuffix("市") != city.removesuffix("市")):
        return False
    if scope.get("date") and str(target_date) != scope["date"]:
        return False
    if scope.get("day_index") and day_index != scope["day_index"]:
        return False
    if scope.get("activity_id") and scope["activity_id"] not in {str(x) for x in target_activity_ids or []}:
        return False
    return True


def project_requirements(records, *, trip_id=None, draft_id=None, topic_id=None, city=None,
                         target_date=None, day_index=None, target_activity_ids=None):
    """Return active applicable dicts; localized tombstones block only this scope.

    Passing no date/day intentionally returns broad requirements only. Call once
    per target day when building day-specific Planner/Recovery input.
    """
    matching = [r for r in valid_records(records) if _matches(r["scope"], trip_id=trip_id,
        draft_id=draft_id, topic_id=topic_id, city=city, target_date=target_date,
        day_index=day_index, target_activity_ids=target_activity_ids)]
    blocked = {old for r in matching for old in r["supersedes"]}
    return [r for r in matching if r["status"] == "active" and r["id"] not in blocked]


def add_requirement(records, *, text, scope, source_ref, key="user_requirement", value=None,
                    strength="soft", revoke=False, supersedes=None):
    result = valid_records(records)
    scope = RequirementScope.model_validate(scope).model_dump(mode="json")
    # A new pace replaces prior pace only where scopes overlap. Parent records
    # stay active for untouched dates; explicit links explain the override.
    replaced = list(supersedes or [])
    for prior in result:
        same_owner = all(prior["scope"].get(k) == scope.get(k) for k in ("trip_id", "draft_id", "topic_id", "city"))
        parent = not prior["scope"].get("day_index") and not prior["scope"].get("date") and not prior["scope"].get("activity_id")
        same_dimension = key not in {"interest", "avoid_category"} or prior.get("value") == value
        if key != "user_requirement" and prior["key"] == key and same_dimension and prior["status"] == "active" and same_owner and (parent or prior["scope"] == scope):
            replaced.append(prior["id"])
    replaced = list(dict.fromkeys(replaced))
    identity = "req_" + uuid5(_NS, f"{source_ref}:{scope}:{key}:{text}:{revoke}").hex
    if any(r["id"] == identity for r in result):
        return result
    for prior in result:
        if prior["id"] in replaced and prior["scope"] == scope:
            prior["status"] = "revoked" if revoke else "superseded"
    record = EffectiveRequirement(id=identity, text=text, key=key, value=value,
        scope=scope, source=RequirementSource(ref=str(source_ref)), strength=strength,
        status="revoked" if revoke else "active", supersedes=replaced)
    return [*result, record.model_dump(mode="json")]


def capture_explicit_requirements(records, text, *, scope, source_ref, force=False, target_day_indices=None):
    """Bounded user-only capture; no suggestion/like/favorite/lock inference.

    Untyped prose is preserved as an explicit statement, not an executable hard
    predicate. Natural-language pace/revocation is deliberately narrow.
    """
    result = valid_records(records)
    if not text.strip() or (not force and (re.search(r"[?？]|吗|是否|怎么样|推荐|收藏|锁定", text)
            or not re.search(r"希望|要求|不要|不想|必须|一定|偏好|喜欢|慢游|轻松|紧凑|取消|撤销|预算|拍照|摄影|步行|少走路", text))):
        return result
    from app.travel_language import chinese_number
    from decimal import Decimal
    # UI-selected day scope covers the whole request. A textual ordinal only
    # scopes its own clause; a later day mention cannot scope earlier interests.
    default_days = target_day_indices or []
    from app.requirement_language import requirement_clauses, clause_polarity
    clauses = requirement_clauses(text)
    for clause_index, clause in enumerate(clauses):
        if not clause.strip():
            continue
        polarity = clause_polarity(clause)
        if polarity == 'historical_reference':
            continue
        local_ordinal = re.search(r"第([一二三四五六七八九十\d]+)天", clause)
        days = target_day_indices or ([chinese_number(local_ordinal[1])] if local_ordinal else default_days)
        scopes = [{**scope, "kind": "day", "day_index": n} for n in days] or [scope]
        revoke = polarity == 'revoke'
        strength = "hard" if re.search(r"必须|(?<!不)一定|不能|禁止|不得", clause) else "soft"
        atoms = []
        pace = re.search(r"慢游|轻松|宽松|少安排|紧凑|充实", clause)
        budget = re.search(r"(?:每日|每天|总)?预算\s*(?:为|是|在|控制在|不超过|最多|上限(?:为)?)?\s*(\d+(?:\.\d{1,2})?)\s*元", clause)
        walking = re.search(r"(?:步行|走路)(?:时间)?\s*(?:不超过|最多|上限|控制在|限制为)?\s*(\d+)\s*分钟", clause)
        if walking is None:
            walking = re.search(r"(?:步行|走路)(?:时间)?(?:上限|限制)?\s*(?:放宽|调整|改|提高)?(?:为|到|成)\s*(\d+)\s*分钟", clause)
        following = clauses[clause_index + 1] if clause_index + 1 < len(clauses) else ""
        relaxed_limit = re.search(r"左右|大概|大约|可以略超|略超|尽量|也可以", clause)
        following_relaxation = following if re.fullmatch(r"\s*(?:可以|允许)?(?:略超|稍微超过|适当超出)(?:一点|一些)?\s*", following) else ""
        limit_strength = "hard" if re.search(r"不超过|最多|上限|限制|控制在|必须|不能|不得", clause) else "soft"
        if relaxed_limit or following_relaxation:
            limit_strength = "soft"
        numeric_text = clause.strip() + ("，" + following_relaxation.strip() if following_relaxation else "")
        if pace:
            atoms.append(("pace", "intensive" if pace[0] in {"紧凑", "充实"} else "relaxed", f"节奏：{pace[0]}", strength))
        if budget:
            budget_key = "daily_budget_fen" if re.match(r"每日|每天", budget[0]) else "budget_fen"
            atoms.append((budget_key, int(Decimal(budget[1]) * 100), numeric_text, limit_strength))
        if re.search(r"拍照|摄影", clause):
            atoms.append(("interest", "photography", "偏好拍照、摄影", strength))
        if walking:
            atoms.append(("max_walking_minutes", int(walking[1]), numeric_text, limit_strength))
        elif re.search(r"少走路|少步行|不想走太多|避免长距离步行", clause):
            atoms.append(("walking_preference", "minimal", "尽量少步行", strength))
        elif revoke and re.search(r"(?:步行|走路)(?:时间|距离)?(?:上限|限制|要求)", clause):
            atoms.append(("max_walking_minutes", None, clause.strip(), "soft"))
        if revoke and not budget and re.search(r"(?:每日|每天|总)?预算(?:上限|限制|要求)?", clause):
            budget_key = "daily_budget_fen" if re.search(r"每日|每天", clause) else "budget_fen"
            atoms.append((budget_key, None, clause.strip(), "soft"))
        for word, category in (("购物", "shopping"), ("美食", "food"), ("自然", "nature"), ("人文", "culture"), ("景点", "sight")):
            if re.search(r"(?:不要|不太想|不想|避免|避开|禁止|不得)(?:安排|去|包含)?" + word, clause):
                avoid_strength = "hard" if strength == "hard" or re.search(r"不要(?:安排|去|包含)?" + word, clause) else "soft"
                if re.search(r"不太想|尽量|如果可以|最好", clause):
                    avoid_strength = "soft"
                atoms.append(("avoid_category", category, f"避免{word}类安排", avoid_strength))
        if not atoms and not revoke:
            atoms.append(("user_requirement", None, clause.strip()[:3000], strength))
        for local in scopes:
            for key, value, atom_text, atom_strength in atoms:
                result = add_requirement(result, text=("撤销：" if revoke else "") + atom_text,
                    scope=local, source_ref=source_ref, key=key, value=value, strength=atom_strength, revoke=revoke)
    return result


def revoke_requirement(records, requirement_id, *, scope=None, source_ref="user-revoke"):
    result = valid_records(records)
    record = next((r for r in result if r["id"] == requirement_id and r["status"] == "active"), None)
    if record is None:
        raise ValueError("active_requirement_not_found")
    if scope is None or RequirementScope.model_validate(scope).model_dump(mode="json") == record["scope"]:
        record["status"] = "revoked"
        return result
    return add_requirement(result, text=f"撤销：{record['text']}", scope=scope, source_ref=source_ref,
        key=record["key"], revoke=True, supersedes=[record["id"]])


def promote_requirements(records, *, draft_id, trip_id, city, start_date):
    result = []
    for record in valid_records(records):
        if record["scope"].get("draft_id") != str(draft_id):
            continue
        scope = {**record["scope"], "draft_id": None, "topic_id": None, "trip_id": str(trip_id), "city": city}
        if scope["kind"] == "draft":
            scope["kind"] = "trip"
        if scope.get("day_index"):
            scope["date"] = (start_date + timedelta(days=scope["day_index"] - 1)).isoformat()
            scope["day_index"] = None
        result.append({**record, "scope": scope})
    return result


def bind_topic_to_trip(records, *, trip_id, city, start_date):
    result = []
    for record in valid_records(records):
        scope = record["scope"]
        if scope.get("draft_id") or (scope.get("trip_id") and scope["trip_id"] != str(trip_id)):
            continue
        if scope.get("city") and scope["city"].removesuffix("市") != city.removesuffix("市"):
            continue
        scope = {**scope, "topic_id": None, "trip_id": str(trip_id), "city": city}
        if scope["kind"] in {"topic", "global_preference"}:
            scope["kind"] = "trip"
        if scope.get("day_index"):
            scope["date"] = (start_date + timedelta(days=scope["day_index"] - 1)).isoformat()
            scope["day_index"] = None
        result.append({**record, "scope": scope})
    return result
