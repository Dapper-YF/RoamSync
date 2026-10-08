"""Small, deterministic guards for quantities that are not place names."""
import re


def chinese_number(value: str) -> int:
    if value.isdigit():
        return int(value)
    digits = {char: index for index, char in enumerate("零一二三四五六七八九")}
    digits["两"] = 2
    if "十" in value:
        tens, _, ones = value.partition("十")
        return digits.get(tens, 1) * 10 + digits.get(ones, 0)
    return digits.get(value, 0)


def trip_duration(text: str) -> int | None:
    matches = list(re.finditer(r"(?<![第一二三四五六七八九十两\d])([一二三四五六七八九十两\d]+)\s*(?:天|日)(?:\s*[一二三四五六七八九十两\d]+\s*晚)?", text))
    # Calendar dates are not trip durations.
    matches = [m for m in matches if not re.search(r"[年月./-]\s*$", text[:m.start()])]
    calendar = r"(?:\d{4}-\d{1,2}-\d{1,2}|\d{1,2}[./]\d{1,2}|\d{1,2}月\d{1,2}[日号]?)"
    ranges = list(re.finditer(calendar + r"\s*(?:至|到|[-—~～])\s*" + calendar, text))
    if matches and ranges and ranges[-1].start() > matches[-1].end():
        return None  # A later explicit date range supersedes the earlier duration.
    return chinese_number(matches[-1][1]) if matches else None


def is_generic_place_quantity(text: str) -> bool:
    value = re.sub(r"\s+", "", text)
    return bool(re.fullmatch(
        r"(?:(?:每天|每日|一天|再|另外|额外|多|少|至少|最多|大约|约|可以|能|安排|游玩|参观|增加|添加|加入|加|的))*"
        r"(?:[一二三四五六七八九十两几\d]+(?:[到至~～—\-或][一二三四五六七八九十两\d]+)?|若干|一些|几个)"
        r"(?:个|处)?(?:大|小|热门|著名|知名|附近|室内|室外)?(?:景点|景区|地点|游览点|活动)(?:左右)?(?:游玩|游览)?", value))
