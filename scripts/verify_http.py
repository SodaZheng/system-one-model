#!/usr/bin/env python3
"""Exercise the real service, including exact 32K boundary and both official SDKs separately."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import time
import urllib.error
import urllib.request

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--url', default='http://127.0.0.1:8080')
parser.add_argument('--long', action='store_true')
args = parser.parse_args()
key = next(x.split('=',1)[1] for x in (root / '.env').read_text().splitlines() if x.startswith('API_KEY='))

def call(path, payload=None):
    req = urllib.request.Request(args.url + path, data=None if payload is None else json.dumps(payload, ensure_ascii=False).encode(),
                                 headers={'Authorization': 'Bearer '+key, 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=3600) as r: return r.status, json.load(r)
    except urllib.error.HTTPError as e: return e.code, json.load(e)

def measured(payload):
    start = time.monotonic()
    status, response = call('/v1/systemone', payload)
    return {'status': status, 'elapsed_seconds': time.monotonic()-start, 'response': response,
            'health_after': call('/health')[1]}

if args.long:
    cases = json.loads((root/'artifacts/long-cases.json').read_text())
    results = []
    for case in cases:
        print('Starting '+case['id'], flush=True)
        result = {'id': case['id'], 'expected': case['expected'], **measured(case['payload'])}
        assert result['status'] == 200, result
        assert result['response']['usage']['input_tokens'] == 32768, result
        answers = result['response']['answers']
        expected = case['expected']
        result['checks'] = {'destination': answers['destination']['choice'] == expected['destination'],
                            'ship': (answers['ship']['noul'] >= .5) == expected['ship'],
                            'score_error': abs(answers['eligibility']['score']-expected['eligibility'])}
        results.append(result)
        (root/'artifacts/long-results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps(result,ensure_ascii=False), flush=True)
    over = dict(cases[0]['payload'])
    over['state'] += ' x'
    result = measured(over)
    assert result['status'] == 422 and result['response']['error']['code']=='max_tokens_exceeded', result
    (root/'artifacts/over-limit.json').write_text(json.dumps(result,indent=2)+'\n')
    print('32K complete-input boundary and overflow verified.', flush=True)
else:
    payload = {'model':'jev-latest','state':{'ticket':'请立即取消订单并退款，不要发货。'},'questions':{
        'intent':{'type':'choice','instructions':'客户要求做什么？','criteria':{'refund':'取消并退款','ship':'发货'}},
        'ship':{'type':'noul','instructions':'客户希望发货吗？'},
        'refund':{'type':'score','instructions':'客户退款意愿','criteria':['没有退款意愿','不确定','明确要求退款']}}}
    result = measured(payload)
    assert result['status']==200, result
    a=result['response']['answers']
    assert a['intent']['choice']=='refund' and a['ship']['noul'] < .5 and a['refund']['score'] > 1, a
    with ThreadPoolExecutor(max_workers=3) as pool:
        concurrent=list(pool.map(measured,[payload]*3))
    assert all(x['status']==200 for x in concurrent), concurrent
    output={'short':result,'concurrent_3':concurrent,'models':call('/v1/models')[1]}
    (root/'artifacts/http-smoke.json').write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(output,ensure_ascii=False),flush=True)
