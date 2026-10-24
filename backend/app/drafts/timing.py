"""Literal local clock provenance shared by proposals and draft preparation."""
import re


def quoted_clocks(quote):
    result = set()
    for match in re.finditer(r"(?<!\d)([01]?\d|2[0-3])(?::([0-5]\d)|(?:点|时)(?:([0-5]?\d)分?|([半整]))?)(?!\d)", quote):
        result.add((int(match[1]), int(match[2] or match[3] or (30 if match[4] == "半" else 0))))
    return result


def explicit_interval(quote, start, end):
    if not start or not end:
        return False
    def present(value):
        hour, minute = (int(part) for part in str(value).split(":")[:2])
        return (hour, minute) in quoted_clocks(quote)
    return present(start) and present(end)
