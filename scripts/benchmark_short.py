import json
import time
import statistics
import urllib.request
from pathlib import Path
root=Path(__file__).resolve().parents[1]
key=next(x.split('=',1)[1] for x in (root/'.env').read_text().splitlines() if x.startswith('API_KEY='))
payload={'model':'jev-latest','state':'客户要求取消订单并退款。','questions':{'refund':{'type':'noul','instructions':'客户要求退款吗？'}}}
samples=[]
for _ in range(6):
 req=urllib.request.Request('http://127.0.0.1:8080/v1/systemone',data=json.dumps(payload).encode(),headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
 t=time.monotonic()
 with urllib.request.urlopen(req,timeout=120) as r: result=json.load(r)
 samples.append(time.monotonic()-t)
 assert result['answers']['refund']['noul']>.5
out={'environment':'Apple Silicon Linux amd64 Rosetta; not native Ubuntu', 'warmup_excluded':samples[0], 'samples_seconds':samples[1:], 'median_seconds':statistics.median(samples[1:]),'tokens':result['usage']['input_tokens'],'questions':1}
(root/'artifacts/short-benchmark.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out),flush=True)
