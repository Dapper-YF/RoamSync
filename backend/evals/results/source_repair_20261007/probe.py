import json,re,hashlib
from pathlib import Path
from datetime import datetime,UTC
from urllib.request import Request,urlopen
from urllib.parse import urljoin
OUT=Path('backend/evals/results/source_repair_20261007')
def fetch(url):
 try:
  with urlopen(Request(url,headers={'User-Agent':'Mozilla/5.0'}),timeout=20) as r:b=r.read(12000000);status=r.status
  text=b.decode('utf-8','replace');return {'url':url,'status':status,'sha256':hashlib.sha256(b).hexdigest(),'body':text}
 except Exception as e:return {'url':url,'error':type(e).__name__,'status':getattr(e,'code',None)}
base='https://www.zjmuseum.com.cn/cn/'
page=fetch(base);rows=[page]
for s in re.findall(r'<script[^>]+src=[\"\x27]([^\"\x27]+)',page.get('body','')):
 if 'app.' in s:
  r=fetch(urljoin(base,s));rows.append(r)
  (OUT/'official_app.js').write_text(r.get('body',''),encoding='utf-8')
  r['endpoint_hints']=re.findall(r'.{0,100}(?:content/[a-zA-Z]+|contentId|content_id|/detail|/getContent).{0,120}',r.get('body',''))[:100]
(OUT/'official_discovery_probe.json').write_text(json.dumps({'time':datetime.now(UTC).isoformat(),'results':rows},ensure_ascii=False,indent=2),encoding='utf-8')
for r in rows: print(r['url'],r.get('status'),r.get('error'),json.dumps(r.get('endpoint_hints',[])[:25],ensure_ascii=False))
