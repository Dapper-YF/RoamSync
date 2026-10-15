from typing import Any


def _infer_day(text: str) -> int | None:
    if "第一天" in text or "首日" in text:
        return 1
    if "第二天" in text:
        return 2
    return None


def _group(
    prefix: str,
    texts: list[str],
    *,
    primary: str,
    operations: list[str],
    route: str,
    clarify: bool,
    day: int | None = None,
    selected_activity: str | None = None,
    tags: tuple[str, ...] = (),
) -> list[dict[str, Any]]:
    return [
        {
            "id": f"{prefix}-{index:02d}",
            "text": text,
            "expected_primary": primary,
            "expected_operations": operations,
            "expected_route": route,
            "should_clarify": clarify,
            "target_day_number": day if day is not None else _infer_day(text),
            "selected_activity": selected_activity,
            "tags": list(tags),
        }
        for index, text in enumerate(texts, 1)
    ]


INTENT_EVAL_CASES: list[dict[str, Any]] = [
    *_group(
        "replan",
        [
            "重新规划整个行程", "全部重排", "从头规划这次旅行", "重做全程安排", "整体重排一下",
            "把整趟旅行重新安排", "重新做一份杭州行程", "这份行程推倒重来", "帮我重新规划全部内容",
            "全程重新规划", "整个安排重做", "重新安排行程", "再规划一次完整行程", "所有天都重新排",
            "请重做这次旅行计划",
        ],
        primary="replan_trip", operations=["replan_trip"], route="plan_preview",
        clarify=False, tags=("normal", "full_trip"),
    ),
    *_group(
        "day",
        [
            "第一天轻松一点", "第一天不要太赶", "第一天下午别太满", "首日放松一点", "首日上午轻松一点",
            "第二天节奏放慢", "第二天不要太满", "第二天下午轻松一点", "第二天晚上别太赶",
            "把第二天安排得松一点", "第一天改得从容一点", "调整第一天的安排", "调整第二天的安排",
            "第二天多留点休息时间", "首日安排得宽松些",
        ],
        primary="replan_trip", operations=["replan_trip"], route="plan_preview",
        clarify=False, tags=("normal", "day_scope"),
    ),
    *_group(
        "add_known",
        [
            "第一天想去小河公园", "第二天想去小河公园", "第一天加入杭州博物馆",
            "第二天添加杭州博物馆", "第一天下午增加雷峰塔", "第二天下午想去中国茶叶博物馆双峰馆区",
            "第一天加入知味观湖滨总店", "第二天添加茶人村龙井路店", "第一天想去绿茶餐厅湖滨店",
            "第二天增加小河公园",
        ],
        primary="add_activity", operations=["add_activity"], route="plan_preview",
        clarify=False, tags=("grounding", "known_place"),
    ),
    *_group(
        "add_unknown",
        [
            "第一天想去故宫", "第二天想去滕王阁", "第一天加入上海博物馆", "第二天添加迪士尼",
            "第一天下午增加一个水族馆", "第二天想去附近的科技馆", "第一天加入某个古镇",
            "第二天添加一家新的咖啡馆", "第一天想去网红展览", "第二天增加海边公园",
        ],
        primary="add_activity", operations=["add_activity"], route="clarify",
        clarify=True, tags=("grounding", "unknown_place", "clarification"),
    ),
    *_group(
        "replace",
        [
            "把第一天的西湖断桥换成小河公园", "把第一天的中国美术学院美术馆替换成杭州博物馆",
            "把第一天的河坊街南宋御街改成雷峰塔", "把第二天的灵隐飞来峰景区换成杭州博物馆",
            "把第二天的龙井村九溪入口替换成小河公园", "第一天把西湖断桥改成雷峰塔",
            "第二天把灵隐飞来峰景区换成中国茶叶博物馆双峰馆区",
            "把第一天下午的中国美术学院美术馆换成小河公园",
            "把第二天下午的龙井村九溪入口改成杭州博物馆",
            "把首日的河坊街南宋御街替换成知味观湖滨总店",
        ],
        primary="replace_activity", operations=["replace_activity"], route="plan_preview",
        clarify=False, tags=("grounding", "replacement", "high_risk"),
    ),
    *_group(
        "remove",
        [
            "删除第一天的西湖断桥", "删掉第一天的中国美术学院美术馆", "取消第一天的河坊街南宋御街",
            "第二天不去灵隐飞来峰景区", "删除第二天的龙井村九溪入口", "删掉首日的西湖断桥",
            "第一天下午删除中国美术学院美术馆", "第二天下午取消龙井村九溪入口",
            "第一天不去河坊街南宋御街", "第二天删掉灵隐飞来峰景区",
        ],
        primary="remove_activity", operations=["remove_activity"], route="plan_preview",
        clarify=False, tags=("grounding", "delete", "high_risk"),
    ),
    *_group(
        "reorder",
        [
            "把第一天的西湖断桥移到下午", "把第一天的中国美术学院美术馆移动到上午",
            "把第一天的河坊街南宋御街提前到下午", "把第二天的灵隐飞来峰景区延后到中午",
            "把第二天的龙井村九溪入口调到上午", "把首日的西湖断桥延后到下午",
            "第一天把中国美术学院美术馆移到晚上", "第二天把灵隐飞来峰景区调到下午",
            "把第一天下午的中国美术学院美术馆提前到上午", "把第二天下午的龙井村九溪入口移到早上",
        ],
        primary="reorder_activities", operations=["reorder_activities"], route="plan_preview",
        clarify=False, tags=("grounding", "reorder"),
    ),
    *_group(
        "readonly",
        [
            "预算是多少", "还剩多少预算", "为什么这样安排", "解释一下第二天的安排", "天气怎么样",
            "你好", "谢谢", "杭州有什么好吃的", "推荐杭州的博物馆", "附近有什么好玩的",
        ],
        primary="mixed", operations=[], route="answer", clarify=False,
        tags=("read_only",),
    ),
    *_group(
        "reject",
        ["帮我订票", "预订酒店", "查一下航班", "删除整个行程", "删除这次旅行"],
        primary="mixed", operations=[], route="reject", clarify=False,
        tags=("unsupported", "safety"),
    ),
    *_group(
        "ambiguous",
        ["调整一下", "删掉这个", "把这个替换成小河公园", "明天下午调整", "调整第九天的安排"],
        primary="mixed", operations=[], route="clarify", clarify=True,
        tags=("ambiguous", "clarification"),
    ),
    *_group(
        "typo",
        [
            "第一天排得太敢了，松点", "把第二天龙井换城小河公园", "第2天想加个杭洲博物馆",
            "首日行成放松一些", "第二天的路现优化一下",
        ],
        primary="mixed", operations=[], route="plan_preview", clarify=False,
        tags=("typo", "model_required"),
    ),
    *_group(
        "multi",
        [
            "第二天把龙井村九溪入口换成小河公园，预算不要增加",
            "第一天加入杭州博物馆并优化路线",
            "第二天下雨，把龙井村九溪入口换成中国茶叶博物馆双峰馆区",
            "重新规划全程，预算降低一些",
            "第一天删掉河坊街南宋御街，再加入小河公园",
        ],
        primary="mixed", operations=[], route="plan_preview", clarify=False,
        tags=("multi_intent",),
    ),
    *_group(
        "reference",
        ["删掉这个", "把这个替换成小河公园", "把这个移到下午", "这个不要动", "这个改到上午"],
        primary="mixed", operations=[], route="plan_preview", clarify=False,
        selected_activity="day1:0", tags=("cross_turn_reference", "grounding"),
    ),
]


_EXPECTED_OVERRIDES: dict[str, dict[str, Any]] = {
    **{f"readonly-{index:02d}": {"expected_primary": "query_trip", "expected_operations": ["query_trip"]} for index in range(1, 6)},
    **{f"readonly-{index:02d}": {"expected_primary": "general_chat", "expected_operations": ["general_chat"]} for index in range(6, 8)},
    **{f"readonly-{index:02d}": {"expected_primary": "search_places", "expected_operations": ["search_places"]} for index in range(8, 11)},
    **{f"reject-{index:02d}": {"expected_primary": "booking_assistance", "expected_operations": ["booking_assistance"]} for index in range(1, 4)},
    **{f"reject-{index:02d}": {"expected_primary": "unsupported", "expected_operations": ["unsupported"]} for index in range(4, 6)},
    "ambiguous-01": {"expected_primary": "replan_trip", "expected_operations": ["replan_trip"]},
    "ambiguous-02": {"expected_primary": "remove_activity", "expected_operations": ["remove_activity"]},
    "ambiguous-03": {"expected_primary": "replace_activity", "expected_operations": ["replace_activity"]},
    "ambiguous-04": {"expected_primary": "replan_trip", "expected_operations": ["replan_trip"]},
    "ambiguous-05": {"expected_primary": "replan_trip", "expected_operations": ["replan_trip"]},
    "typo-01": {"expected_primary": "replan_trip", "expected_operations": ["replan_trip"]},
    "typo-02": {"expected_primary": "replace_activity", "expected_operations": ["replace_activity"]},
    "typo-03": {"expected_primary": "add_activity", "expected_operations": ["add_activity"], "expected_route": "clarify", "should_clarify": True},
    "typo-04": {"expected_primary": "replan_trip", "expected_operations": ["replan_trip"]},
    "typo-05": {"expected_primary": "optimize_route", "expected_operations": ["optimize_route"]},
    "multi-01": {"expected_primary": "replace_activity", "expected_operations": ["replace_activity", "adjust_budget"]},
    "multi-02": {"expected_primary": "add_activity", "expected_operations": ["add_activity", "optimize_route"]},
    "multi-03": {"expected_primary": "replace_activity", "expected_operations": ["replace_activity", "weather_replan"]},
    "multi-04": {"expected_primary": "replan_trip", "expected_operations": ["replan_trip", "adjust_budget"]},
    "multi-05": {"expected_primary": "remove_activity", "expected_operations": ["remove_activity", "add_activity"]},
    "reference-01": {"expected_primary": "remove_activity", "expected_operations": ["remove_activity"]},
    "reference-02": {"expected_primary": "replace_activity", "expected_operations": ["replace_activity"]},
    "reference-03": {"expected_primary": "reorder_activities", "expected_operations": ["reorder_activities"]},
    "reference-04": {"expected_primary": "replan_trip", "expected_operations": ["replan_trip"]},
    "reference-05": {"expected_primary": "reorder_activities", "expected_operations": ["reorder_activities"]},
}
for _case in INTENT_EVAL_CASES:
    _case.update(_EXPECTED_OVERRIDES.get(_case["id"], {}))

next(case for case in INTENT_EVAL_CASES if case["id"] == "typo-02").update(
    {"expected_route": "clarify", "should_clarify": True}
)


assert len(INTENT_EVAL_CASES) == 115
