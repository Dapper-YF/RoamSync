"""Read-only public official CMS audit; no application-state operations."""
import concurrent.futures
import hashlib
import json
from datetime import UTC, datetime
from urllib.parse import urlencode
from urllib.request import Request, urlopen

def fetch(job):
    url, data, form = job
    result = {"url": url, "request_body": data, "retrieved_at": datetime.now(UTC).isoformat()}
    body = (urlencode(data) if form else json.dumps(data)).encode()
    try:
        request = Request(url, data=body, headers={"Content-Type": "application/x-www-form-urlencoded" if form else "application/json"})
        with urlopen(request, timeout=20) as response:
            raw = response.read(2_000_000)
            result.update(status=response.status, bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
        result["response"] = json.loads(raw)
    except Exception as exc:
        result["error_type"] = type(exc).__name__
        result["error_status"] = getattr(exc, "code", None)
    return result

jobs = [("https://www.njmuseum.com/api/home/info", {"language": "zh"}, True),
        ("https://www.njmuseum.com/api/news/freshNotice", {"language": "zh"}, True),
        ("https://www.njmuseum.com/api/visit/notes", {"language": "zh"}, True),
        ("https://www.zjmuseum.com.cn/api/category/list", {"siteId": 22}, False)]
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
    print(json.dumps(list(executor.map(fetch, jobs)), ensure_ascii=False, indent=2))
