"""Deterministic, visible metadata decisions; retrieval never infers filters."""
import re
from app.companion_facts import forecast_intent

from app.companion_contracts import CompanionContext, CompanionSuggestion, InformationNeed


def is_formal_decision_question(text: str) -> bool:
    return bool(re.search(r"为什么|为何|理由|解释", text) and re.search(
        r"安排|放在|放到|放.{0,15}晚上|行程|\d{1,2}\s*(?:点|时|[:：]\d{2})", text))


def explicit_destination(text: str) -> str | None:
    # Small explicit vocabulary, not geographical entity resolution. Unknown
    # destinations retain Phase 1's raw context and cannot acquire place IDs.
    if "西湖" in text and not re.search(r"苏州|北京|上海|成都", text):
        return "杭州"  # Corpus place scope only; never a formal place identity.
    cities = [city for city in ("杭州", "苏州", "北京", "上海", "成都") if city in text]
    return cities[0] if len(cities) == 1 else None


def determine_information_need(context: CompanionContext, selected: list[CompanionSuggestion]) -> InformationNeed:
    text, goal = context.current_message, context.travel_goal
    topic_patterns = {
        "lake_formation_year": r"(?:形成|诞生).{0,8}(?:哪年|哪一年|什么时候|何时|几几年|年份|年代)|(?:哪年|哪一年|什么时候|何时).{0,8}(?:形成|诞生)",
        "lake_formation_history": r"形成|诞生|起源",
        "heritage_inscription_year": r"(?:哪年|哪一年|什么时候|何时|年份).{0,12}(?:列入|申遗|世界遗产|遗产名录)|(?:列入|申遗|世界遗产|遗产名录).{0,12}(?:哪年|哪一年|什么时候|何时|年份)",
        "west_lake_construction_period": r"(?:建造|修建|兴建|营建|建于|开凿|疏浚).{0,12}(?:哪年|哪一年|何时|什么时候|几年|年代|朝代)|(?:哪年|哪一年|何时|什么时候|年代|朝代).{0,12}(?:建造|修建|兴建|开凿)",
        "dynasty_history": r"朝代|哪一朝|哪个朝代",
        "historical_figures": r"历史人物|哪些人|谁.{0,8}(?:建造|修建|创建|提出)|人物故事|哪些诗人|哪位诗人",
        "fame_reasons": r"为什么.{0,8}(?:有名|闻名|著名)|因何.{0,6}(?:闻名|有名)|出名原因",
        "cultural_significance": r"文化意义|历史意义|文化影响|历史影响|山水美学",
        "history_general": r"历史|文化|来历|传说|背景|发展史|演变",
        "landscape_components": r"景观.{0,8}(?:包含|构成|组成|要素)|(?:构成|组成).{0,8}(?:景观|哪些部分)|自然和人工要素",
        "landscape_influence": r"园林设计.{0,8}影响|影响.{0,8}园林",
        "photography_authority": r"(?:UNESCO|联合国教科文|官方).{0,14}(?:摄影|机位|推荐)|(?:摄影|机位).{0,14}(?:UNESCO|联合国教科文|官方).{0,8}(?:推荐|认为)",
        "photography_elements": r"摄影|拍摄|构图|机位|取景",
        "photography_time": r"(?:摄影|拍照|光线).{0,12}(?:时段|傍晚|最好)|(?:傍晚|最好).{0,12}(?:摄影|拍照|光线)",
        "photography_scope": r"整个城市.{0,8}摄影|全城.{0,8}摄影",
        "senior_destination_suitability": r"(?:杭州|目的地|城市|西湖).{0,12}(?:适合|最适合).{0,6}(?:老人|长辈|父母)|(?:适合|最适合).{0,8}(?:老人|长辈|父母).{0,8}(?:城市|杭州)|证明.{0,12}适合",
        "senior_activity_guidance": r"老年旅游服务规范|老年旅游规范|活动强度|高强度",
        "senior_continuous_visit_time": r"连续游览|游览多久|休息多久",
        "senior_slow_travel": r"带父母|带老人|带长辈|慢游.{0,6}(?:长辈|父母)|长辈.{0,8}(?:节奏|舒缓)",
        "autumn_custom": r"秋季|秋天|赏桂|桂花",
        "local_tea_lifestyle": r"茶馆|茶楼|喝茶|茶文化",
        "daily_local_tea_generalization": r"(?:所有|每个|全部).{0,8}(?:本地人|当地人).{0,8}(?:每天|每日).{0,8}喝茶",
        "destination_scope": r"全部的自然风景|整个城市都|全杭州",
        "source_page_title": r"原文标题|原始标题|文章标题|页面标题|标题是什么",
    }
    requested_topics = [topic for topic, pattern in topic_patterns.items() if re.search(pattern, text, re.I)]
    # Stable subject families; artificial landscape periods are not geology.
    artificial_period = bool(re.search(r"(?:堤岛|堤道|人工岛|岛群|两堤|三岛).{0,24}(?:世纪|年代|时期|形成|营造|疏浚|出现)|(?:疏浚|营造).{0,16}(?:堤|岛)", text))
    families = {
        "west_lake_construction_period": artificial_period,
        "landscape_components": bool(re.search(r"山体|山峦|湖山|自然.{0,8}(?:人工|骨架)|人工建筑|寺.{0,4}塔|景观(?:清单|组成|概括)", text)) and not artificial_period,
        "heritage_inscription_year": bool(re.search(r"(?:申遗|遗产).{0,10}(?:登记|时间线)|(?:登记|何时).{0,12}(?:遗产|申遗)", text)),
        "local_tea_lifestyle": bool(re.search(r"茶舍|茶空间|品茶|吴山|北山路", text)),
        "senior_continuous_visit_time": bool(re.search(r"(?:一次|连续).{0,12}(?:游览|逛|步行).{0,8}(?:多久|时长|上限)|(?:游览|逛).{0,10}(?:休息|不歇脚|时长)", text)),
        "senior_slow_travel": bool(re.search(r"连续.{0,5}(?:乘车|坐车)", text)),
        "source_page_title": bool(re.search(r"网页(?:名|名称)|页面名|发布机构|原始页面标题|提供URL|链接", text,re.I)),
    }
    for topic, matched in families.items():
        if matched and topic not in requested_topics:
            requested_topics.append(topic)
    if artificial_period and not re.search(r"地质|湖盆|自然起源|准确年份|精确.{0,6}年份", text):
        requested_topics = [t for t in requested_topics if t not in {"lake_formation_year", "lake_formation_history"}]
    history_topics = {"lake_formation_year", "lake_formation_history", "heritage_inscription_year",
        "west_lake_construction_period", "dynasty_history", "historical_figures", "fame_reasons",
        "cultural_significance", "history_general"}
    history = bool(history_topics.intersection(requested_topics) or re.search(
        r"(?:哪年|哪一年|年份|年代|年间|世纪|历史|文化|来历|起源|传说|背景|形成|诞生|建造|兴建|修建|营建|建于|朝代|人物|何时|为什么.{0,8}有名|因何.{0,6}闻名|文化意义|历史意义)", text))
    if history and not history_topics.intersection(requested_topics):
        requested_topics.insert(0, "history_general")
    decision = is_formal_decision_question(text) or bool(re.search(r"为什么|理由|解释", text) and
        (selected or re.search(r"之前|刚才|安排|放在|推荐", text)))
    itinerary = is_formal_decision_question(text) or (not selected and (
        (decision and bool(re.search(r"安排|放在|行程|晚上|上午", text)))
        or bool(re.search(r"当前行程|目前行程|现在.{0,6}行程|第[一二三四五六七八九十\d]+天", text))))
    prefs = not history and goal.goal_type in {"recommendation", "comparison", "travel_advice", "destination_discovery"}
    preference_only = bool(context.relevant_user_preferences and re.search(r"我.*(?:喜欢|偏好)|不喜欢", text)
                           and not re.search(r"[？?]|吗|为什么|有哪些|有什么", text))
    fact_patterns = {"weather": r"天气|下雨|降雨|气温|日落|日出", "opening_hours": r"开门|关门|几点关|开放时间|营业|闭馆|闭园",
        "price": r"票价|门票|多少钱|价格|余票|预约", "traffic": r"路况|ETA|GPS|多久能到|堵车|班次",
        "execution": r"玩.{0,5}多久|待.{0,5}多久|停留.{0,5}多久|走.{0,5}多久"}
    fact_types = [key for key, pattern in fact_patterns.items() if re.search(pattern, text, re.I)]
    if re.search(r"花况|今年.{0,12}(?:桂花季|桂花节|赏桂|活动).{0,8}(?:几点|什么时候|开始)", text):
        fact_types.append("current_seasonal_conditions")
    if re.search(r"(?:此刻|本周|现在|当前).{0,18}(?:桂花|花开)|(?:桂花|花开).{0,18}(?:此刻|本周|现在|当前)", text):
        fact_types.append("current_seasonal_conditions")
    if re.search(r"今天.{0,8}(?:桂花|花开|开花|花况)|(?:桂花|花开|开花).{0,8}(?:今天|现在|当前)|今年.{0,8}(?:桂花季|活动).{0,8}(?:几点|什么时候)", text):
        fact_types.append("current_seasonal_conditions")
    if decision and re.search(r"\d{1,2}\s*(?:点|时|[:：]\d{2})", text):
        fact_types.append("timing_conditions")
    if forecast_intent(text) and "weather" not in fact_types:
        fact_types.append("weather")
    live = goal.live_fact_likely_required or bool(fact_types)
    if live and not fact_types:
        fact_types = ["current_conditions"]
    seasons = [tag for tag, pattern in (("spring", "春天|春季"), ("summer", "夏天|夏季"),
        ("autumn", "秋天|秋季|秋日"), ("winter", "冬天|冬季")) if re.search(pattern, text)]
    senior = bool(re.search(r"父母|老人|长辈|老年", text) and not re.search(r"不带父母|不是带父母|不带老人", text))
    types = []
    if history:
        types.append("history_culture")
    if re.search(r"当地生活|本地生活|生活体验|市井|烟火|茶馆|喝茶|茶文化|茶楼", text):
        types.append("local_lifestyle")
    if seasons:
        types.append("seasonal_experience")
    if senior:
        types.extend(["audience_strategy", "travel_strategy"])
    elif re.search(r"轻松|慢游|节奏|怎么游|怎么玩", text):
        types.append("travel_strategy")
    if re.search(r"摄影|拍摄|机位|构图", text):
        types.append("place_experience")
    if "landscape_components" in requested_topics or "landscape_influence" in requested_topics:
        types.append("destination_profile")
    if "source_page_title" in requested_topics and not types:
        types.extend(["history_culture", "destination_profile"])
    if "local_tea_lifestyle" in requested_topics and "local_lifestyle" not in types:
        types.append("local_lifestyle")
    if "autumn_custom" in requested_topics and "seasonal_experience" not in types:
        types.append("seasonal_experience")
    if not types:
        types = ["place_experience" if goal.goal_type == "recommendation" else
                 "destination_profile" if goal.goal_type in {"comparison", "destination_exploration"} else "travel_strategy"]
    # Interaction acknowledgments and saved original rationale need no RAG.
    # Generic destination discovery and solo-travel advice do not need corpus
    # lookup until there is a destination or a concrete factual question.
    destination_named = bool(context.current_destination or explicit_destination(text))
    # Stable conversation uses the model's general knowledge by default. The
    # tiny reviewed corpus is an explicit evidence tool, not a coverage gate.
    source_text = re.sub(r"(?:不用|不需要|无需)(?:给|提供)?(?:出处|来源|资料)", "", text)
    general_knowledge_allowed = not (
        live or decision or re.search(r"来源|出处|官方|证据|依据|引用|资料|文献|核实|确切|可靠材料|查证|核对|证实|核查|(?:按|据|依).{0,6}规范", source_text))
    stable_in_live = bool(live and requested_topics and not decision and
        re.search(r"历史|文化|传统|民俗|习俗|影响|景观|组成|堤|岛|茶|游览|申遗|遗产|报道|页面", text))
    knowledge = (history or (goal.knowledge_required and destination_named) or bool(seasons) or senior
        or bool(requested_topics) or bool(re.search(r"当地生活|生活体验|市井|茶馆|来源|出处|资料|依据|核实", text))) and not preference_only and not decision and (not live or stable_in_live) and not general_knowledge_allowed
    advice_intent = bool(re.search(r"推荐|建议|怎么游|怎么玩|怎么安排|适合|值得|轻松|摄影|体验", text)) or (not requested_topics and goal.goal_type in {"recommendation", "travel_advice"})
    if re.search(r"不(?:需要|要)(?:游玩)?建议|不要推荐|只接受.{0,6}证据|只按.{0,8}(?:证据|资料|出处)", text):
        advice_intent = False
    if "senior_destination_suitability" in requested_topics and re.search(r"证明|能否推出|是不是|一定|最适合", text) and not re.search(r"给我.{0,6}(?:建议|推荐)|怎么游|怎么玩|如何安排", text):
        advice_intent = False
    if "photography_authority" in requested_topics and not re.search(r"给我.{0,6}(?:建议|推荐)|怎么拍|如何拍", text):
        advice_intent = False
    requests_source_fact = bool(requested_topics)
    answer_mode = "mixed" if requests_source_fact and advice_intent else "factual" if requests_source_fact else "advisory"
    return InformationNeed(knowledge_required=knowledge, general_knowledge_allowed=general_knowledge_allowed,
        knowledge_types=list(dict.fromkeys(types)) if knowledge else [],
        live_fact_required=live, forecast_required=forecast_intent(text) and not decision,
        fact_types=fact_types, decision_history_required=decision,
        # Preferences can be read directly; do not load the current Trip merely
        # to fill an exploration destination or missing planning slots.
        trip_context_required=itinerary,
        preferences_required=prefs, itinerary_required=itinerary,
        season_tags=seasons, audience_tags=["senior"] if senior else [],
        filter_signals=(["explicit_season"] if seasons else []) + (["parent_word_to_senior_filter_not_age_fact"] if senior else []),
        answer_mode=answer_mode, requested_fact_topics=requested_topics)
