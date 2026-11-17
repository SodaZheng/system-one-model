"""Compare chunked vs whole-prefill probabilities using the same real checkpoint."""
import json
import time
from app.protocol import RequestBody, encode
from app.runtime import Runtime
import torch
runtime = Runtime()
body = RequestBody.model_validate({'state': 'The approved color is blue.\n' + 'Unrelated record, ignore this line.\n' * 120,
    'questions': {'color': {'type': 'choice', 'instructions': 'What color was approved?', 'criteria': {'red': None, 'blue': None}},
                  'ok': {'type': 'noul', 'instructions': 'Was blue approved?'},
                  'level': {'type': 'score', 'instructions': 'How clear is the color evidence?', 'criteria': ['absent', 'clear']}}})
built, keys = encode(runtime.tokenizer, body)
t = time.monotonic()
chunked = runtime.logits(built, 512)
# Independent monolithic, cache-disabled upstream-style forward path.
with torch.inference_mode():
    hidden = runtime.model.model(input_ids=torch.tensor([built['ids']]), use_cache=False).last_hidden_state
    whole = torch.nn.functional.linear(hidden[0, built['slots']], runtime.weights).float()
errors = []
for i, labels in enumerate(keys):
    a, b = [torch.softmax(x[i, :len(labels)], -1) for x in (chunked, whole)]
    errors.append(float((a-b).abs().max()))
result = {'tokens': len(built['ids']), 'max_probability_error': max(errors), 'tolerance': .0002,
          'passed': max(errors) < .0002, 'elapsed_seconds': time.monotonic()-t}
print(json.dumps(result), flush=True)
open('/workspace/artifacts/parity.json', 'w').write(json.dumps(result, indent=2)+'\n')
assert result['passed'], result
