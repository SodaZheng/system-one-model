"""Create exact-token HTTP cases, counting shared state plus every question/option."""
import json
from pathlib import Path
from transformers import AutoTokenizer
from app.protocol import RequestBody, encode

root = Path('/workspace')
tok = AutoTokenizer.from_pretrained(root / 'models/this-that-1.2', local_files_only=True)
cases = []
for lang, location in [('en', 'head'), ('zh', 'tail')]:
    if lang == 'en':
        evidence = 'Authoritative shipping record: order ZX-731 has destination Oslo and status CANCELLED. Cancelled orders must not be shipped.\n'
        questions = {
            'destination': {'type': 'choice', 'instructions': 'What is the destination of order ZX-731?', 'criteria': {'oslo': 'Oslo', 'rome': 'Rome', 'paris': 'Paris'}},
            'ship': {'type': 'noul', 'instructions': 'Should order ZX-731 be shipped according to the shipping record?'},
            'eligibility': {'type': 'score', 'instructions': 'Rate shipping eligibility of order ZX-731.', 'criteria': ['must not ship', 'requires review', 'may ship']}}
        filler = 'Routine warehouse maintenance is complete. This entry is unrelated to shipping orders.\n'
        expected = {'destination': 'oslo', 'ship': False, 'eligibility': 0}
    else:
        evidence = '唯一有效的订单记录：订单 QX-916 的目的地是深圳，状态为已批准，已完成付款，允许出库。\n'
        questions = {
            'destination': {'type': 'choice', 'instructions': '订单 QX-916 的目的地是哪里？', 'criteria': {'shenzhen': '深圳', 'beijing': '北京', 'shanghai': '上海'}},
            'ship': {'type': 'noul', 'instructions': '根据唯一有效的订单记录，订单 QX-916 是否允许出库？'},
            'eligibility': {'type': 'score', 'instructions': '评价订单 QX-916 的出库资格。', 'criteria': ['禁止出库', '需要复核', '允许出库']}}
        filler = '仓库日常设备检查已经完成。这条日志与订单状态和目的地无关。\n'
        expected = {'destination': 'shenzhen', 'ship': True, 'eligibility': 2}
    def body(n, pad=0):
        background = filler * n + ' x' * pad + '\n'
        state = evidence + background if location == 'head' else background + evidence
        return {'model': 'jev-latest', 'state': state, 'questions': questions}
    lo, hi = 0, 32768
    while lo + 1 < hi:
        mid = (lo + hi)//2
        try: encode(tok, RequestBody.model_validate(body(mid))); lo = mid
        except Exception: hi = mid
    payload = body(lo)
    length = len(encode(tok, RequestBody.model_validate(payload))[0]['ids'])
    for pad in range(max(0, 32768-length-5), 32768-length+8):
        try:
            candidate = body(lo, pad)
            length2 = len(encode(tok, RequestBody.model_validate(candidate))[0]['ids'])
            if length2 == 32768: payload = candidate; break
        except Exception: pass
    actual = len(encode(tok, RequestBody.model_validate(payload))[0]['ids'])
    assert actual == 32768, actual
    cases.append({'id': lang+'-'+location+'-32768', 'tokens': actual, 'expected': expected, 'payload': payload})
path = root / 'artifacts/long-cases.json'
path.write_text(json.dumps(cases, ensure_ascii=False, indent=2))
print(json.dumps([{k:v for k,v in c.items() if k!='payload'} for c in cases], ensure_ascii=False))
