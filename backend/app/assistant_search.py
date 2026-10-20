"""Bounded, explicit read-only web search. Search snippets never become verified facts.

Images originate exclusively in this response, never model-authored URLs or past turns.
No remote image downloading, new tables, or independent media store.
"""
import ipaddress
import re
from urllib.parse import urlsplit, unquote

from app.external_facts import ExternalFactError, search_tavily


def public_image_url(value):
    if not isinstance(value, str) or len(value) > 2000:
        return None
    try:
        url = urlsplit(value)
        if url.scheme != "https" or not url.hostname or url.username or url.password:
            return None
        if url.hostname.lower() in {"localhost", "localhost.localdomain"} or url.hostname.endswith((".local", ".internal")):
            return None
        try:
            if not ipaddress.ip_address(url.hostname).is_global:
                return None
        except ValueError:
            if "." not in url.hostname:
                return None
        if re.search(r"(?:token|signature|api[_-]?key|password)=", url.query, re.I):
            return None
    except ValueError:
        return None
    return value


def search_requested(message):
    return bool(re.search(r"联网(?:查|搜)|(?:web|网络)\s*search|网上(?:查|搜)|搜索.{0,12}(?:资料|图片|美食|街区|景点|氛围)|查资料", message, re.I))


def search_subject(message):
    text = message.strip()
    prefix = r"^(?:请|帮我|给我|联网|网络|网上|搜索|查询|查找|查资料|查|搜|一下|关于|看看|Web\s*search|[\s，,:：])+"
    text = re.sub(prefix, "", text, flags=re.I)
    # Prefer the complete named subject, not just its containing city. Unknown
    # phrasing yields no images rather than guessing a different place.
    return re.split(r"有什么|有哪些|怎么样|适合|是否|的(?:图片|照片|美食|街头|氛围|特色)|[？?，,。\s]", text, maxsplit=1)[0][:80]


def project_search(fact, message):
    sources = []
    for item in fact.payload.get("results", [])[:5]:
        if not isinstance(item, dict) or not public_image_url(item.get("url")):
            continue
        sources.append({"url": item["url"], "title": str(item.get("title", ""))[:240], "excerpt": str(item.get("content", ""))[:1000]})
    images = []
    # Score comes from the image-search provider. Description must share an
    # explicit subject with this turn; no fuzzy model relevance assertion.
    subject = search_subject(message)
    visual = bool(re.search(r"美食|火锅|串串|街区|街头|城市|氛围|景点|风景|公园|图片|看看|适合.*逛", message))
    for item in fact.payload.get("images", [])[:12]:
        if not visual or not sources or not isinstance(item, dict):
            continue
        url = public_image_url(item.get("url"))
        description = str(item.get("description") or "")[:300]
        filename = unquote(urlsplit(url).path.rsplit("/", 1)[-1]) if url else ""
        identity_text = description + " " + filename
        exact_subject = len(subject) >= 2 and subject.casefold() in identity_text.casefold()
        # For an explicitly requested food illustration the dish is the subject,
        # not proof of where a stock/reference photograph was taken. Never apply
        # this fallback to a venue or city-atmosphere photograph.
        dish = next((name for name, pattern in (("火锅", r"火锅|hot[ -]?pot"), ("串串", r"串串|skewers?"))
            if name in message and re.search(pattern, identity_text, re.I)), None)
        if not url or not (exact_subject or dish):
            continue
        if re.search(r"美食|火锅|串串|小吃", message) and not re.search(r"美食|火锅|串串|小吃|food|hot.?pot|snack", identity_text, re.I):
            continue
        if not description:
            description = re.sub(r"\.(?:jpe?g|png|webp|gif)$", "", filename, flags=re.I)[:160]
        if isinstance(item.get("score"), (int, float)) and item["score"] < 0.6:
            continue
        if url not in {i["url"] for i in images}:
            # Original image URL is the only guaranteed attribution available in
            # Tavily image results. Do not invent a publisher or license.
            images.append({"url": url, "description": description if exact_subject else f"{dish}参考图 · {description}", "source_url": url,
                "topic": subject if exact_subject else dish})
        if len(images) == 3:
            break
    return {"status": "available" if sources else "empty", "provider": "tavily", "queried_at": fact.queried_at,
        "sources": sources, "images": images, "semantics": "search_reference_not_verified_fact"}


async def search_for_answer(settings, message):
    try:
        fact = await search_tavily(settings, query=message, max_results=4, include_images=True)
        return project_search(fact, message)
    except ExternalFactError as exc:
        return {"status": "unavailable", "sources": [], "images": [], "provider": "tavily",
            "error_code": str(exc) if str(exc) in {"search_authentication_failed", "search_provider_unavailable", "tavily provider is not configured"} else "search_provider_unavailable"}
