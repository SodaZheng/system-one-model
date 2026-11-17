#!/usr/bin/env python3
"""Target-machine HTTP verification. No third-party Python dependencies required."""
import argparse
import datetime
import json
from pathlib import Path
import time
import urllib.error
import urllib.request

root=Path(__file__).resolve().parent
parser=argparse.ArgumentParser()
parser.add_argument('--long',action='store_true',help='Run both exact 32K cases; may take many minutes on CPU')
parser.add_argument('--url',default='http://127.0.0.1:8080')
a=parser.parse_args()
key=next(x.split('=',1)[1] for x in (root/'.env').read_text().splitlines() if x.startswith('API_KEY='))
if a.long:
 cases=json.loads((root/'long-cases.json').read_text())
else:
 cases=[{'id':'short-refund','payload':{'model':'jev-latest','state':'客户要求取消订单并退款。','questions':{'refund':{'type':'noul','instructions':'客户要求退款吗？'}}}}]
results=[]
output=root/('verification-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'.json')
for case in cases:
 print('Running '+case['id'],flush=True)
 req=urllib.request.Request(a.url+'/v1/systemone',data=json.dumps(case['payload'],ensure_ascii=False).encode(),headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
 t=time.monotonic()
 try:
  with urllib.request.urlopen(req,timeout=3600) as r: status,response=r.status,json.load(r)
 except urllib.error.HTTPError as e: status,response=e.code,json.load(e)
 result={'id':case['id'],'status':status,'elapsed_seconds':time.monotonic()-t,'response':response}
 results.append(result)
 output.write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
 assert status==200,result
 if a.long:
  assert response['usage']['input_tokens']==32768,result
  expected=case['expected']; answers=response['answers']
  result['checks']={'destination':answers['destination']['choice']==expected['destination'],
                    'ship':(answers['ship']['noul']>=.5)==expected['ship'],
                    'score_error':abs(answers['eligibility']['score']-expected['eligibility'])}
 else: assert response['answers']['refund']['noul']>.5,result
 output.write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps(result,ensure_ascii=False),flush=True)
print('Saved '+str(output))
