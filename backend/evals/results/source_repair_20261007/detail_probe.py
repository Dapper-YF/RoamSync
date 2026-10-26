import json,hashlib
from pathlib import Path
from urllib.request import Request,urlopen
from datetime import datetime,UTC
out=Path('backend/evals/results/source_repair_20261007')
body={'categoryCode':'Notice','siteId':22,'contentId':39496}
url='https://www.zjmuseum.com.cn/api/content/detail'
try:
 with urlopen(Request(url,data=json.dumps(body).encode(),headers={'Content-Type':'application/json'}),timeout=20) as r:raw=r.read(3000000);status=r.status
 value=json.loads(raw)
 evidence={'fetched_at':datetime.now(UTC).isoformat(),'url':url,'request':body,'http_status':status,'sha256':hashlib.sha256(raw).hexdigest(),'response':value}
except Exception as e:evidence={'url':url,'error':type(e).__name__,'http_status':getattr(e,'code',None)}
(out/'zhejiang_39496_detail.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(evidence,ensure_ascii=False))
