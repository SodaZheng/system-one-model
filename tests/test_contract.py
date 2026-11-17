import gzip
import json
import math
import os
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import httpx
import zstandard
from fastapi.testclient import TestClient
from app.protocol import APIError, Choice, Score, RequestBody, encode, render
from app.server import create_app

BASE = {'state': {'message': '请退款'}, 'questions': {'ok': {'type': 'noul', 'instructions': '需要退款吗？'}}}

class FakeRuntime:
    max_tokens = 32768
    threads = 8
    chunk_size = 512
    completed_requests = 0
    def predict(self, body):
        if body.state == 'slow': time.sleep(.2)
        if body.state == 'over': raise APIError(422, 'max_tokens_exceeded', 'Too long, no truncation.')
        if body.state == 'error': raise RuntimeError('test failure')
        self.completed_requests += 1
        return {'model': 'this-that-model-1.2', 'answers': {'ok': {'type': 'noul', 'noul': .9}},
                'usage': {'input_tokens': 20, 'output_tokens': 1}}

class ContractTests(unittest.TestCase):
    def setUp(self):
        os.environ['API_KEY'] = 'test-key'
        os.environ['MAX_QUEUED_REQUESTS'] = '1'
        self.client = TestClient(create_app(FakeRuntime))
        self.client.__enter__()
        self.headers = {'Authorization': 'Bearer test-key'}
    def tearDown(self): self.client.__exit__(None, None, None)
    def post(self, body, **kwargs):
        return self.client.post('/v1/systemone', json=body, headers=self.headers, **kwargs)
    def test_auth_and_health(self):
        self.assertEqual(self.client.get('/health').status_code, 200)
        self.assertEqual(self.client.get('/v1/models').status_code, 401)
        self.assertIn('models', self.client.get('/v1/models', headers=self.headers).json())
    def test_routes_aliases_and_multilingual_json(self):
        for model in ['jev-latest', 'jev-preview', 'jev-1.14', 'thisthat']:
            r = self.post({**BASE, 'model': model})
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(r.json()['model'], 'this-that-model-1.2')
        self.assertEqual(self.post({**BASE, 'model': 'typo'}).status_code, 404)
        self.assertEqual(self.client.post('/v1/v1/systemone', json=BASE, headers=self.headers).status_code, 200)
    def test_compression(self):
        raw = json.dumps(BASE).encode()
        for encoding, body in [('gzip', gzip.compress(raw)), ('zstd', zstandard.ZstdCompressor().compress(raw))]:
            r = self.client.post('/v1/systemone', content=body, headers={**self.headers, 'Content-Type': 'application/json', 'Content-Encoding': encoding})
            self.assertEqual(r.status_code, 200, r.text)
        bomb = zstandard.ZstdCompressor().compress(b'x' * (3 * 1024**2))
        r = self.client.post('/v1/systemone', content=bomb, headers={**self.headers, 'Content-Type': 'application/json', 'Content-Encoding': 'zstd'})
        self.assertEqual(r.status_code, 413)
    def test_invalid_and_unsupported_requests(self):
        for body in [{**BASE, 'state': None}, {**BASE, 'questions': {}}, {**BASE, 'questions': {'x': {'type': 'score', 'criteria': []}}}]:
            self.assertEqual(self.post(body).status_code, 422)
        for body in [{**BASE, 'assets': {'image': {'type': 'image'}}}, {**BASE, 'questions': {'x': {'type': 'box'}}}]:
            r = self.post(body)
            self.assertEqual(r.status_code, 422)
            self.assertEqual(r.json()['error']['code'], 'unsupported_modality')
        self.assertEqual(self.post({**BASE, 'state': 'over'}).json()['error']['code'], 'max_tokens_exceeded')
    def test_bounded_queue_and_health_during_inference(self):
        with ThreadPoolExecutor(max_workers=3) as pool:
            a = pool.submit(self.post, {**BASE, 'state': 'slow'})
            deadline = time.monotonic() + 3
            while not self.client.get('/health').json()['busy'] and time.monotonic() < deadline: time.sleep(.005)
            b = pool.submit(self.post, {**BASE, 'state': 'slow'})
            while self.client.get('/health').json()['queued_requests'] != 1 and time.monotonic() < deadline: time.sleep(.005)
            r = self.post(BASE)
            self.assertEqual(r.status_code, 429)
            self.assertEqual(r.headers['retry-after'], '5')
            self.assertEqual(a.result().status_code, 200)
            self.assertEqual(b.result().status_code, 200)
    def test_worker_survives_failed_request(self):
        self.assertEqual(self.post({**BASE, 'state': 'error'}).status_code, 500)
        self.assertEqual(self.post(BASE).status_code, 200)
    def test_choice_confidence(self):
        q = Choice(type='choice', criteria={'a': None, 'b': None, 'c': None})
        a = render(q, ['a','b','c'], [.6,.3,.1])
        self.assertAlmostEqual(a['confidence'], .4)
        self.assertEqual(a['choice'], 'a')
    def test_score_expected_value_and_distance_confidence(self):
        q = Score(type='score', criteria=['low', {'level':'medium'}, 'high'])
        a = render(q, ['0','1','2'], [0,.5,.5])
        self.assertAlmostEqual(a['score'], 1.5)
        self.assertAlmostEqual(a['confidence'], .25)
        self.assertEqual(a['legend']['1'], {'level':'medium'})
        self.assertEqual(render(q, ['0','1','2'], [.5,0,.5])['confidence'], 0)
    def test_single_option(self):
        q = Score(type='score', criteria=['only'])
        self.assertEqual(render(q, ['0'], [1])['score'], 0)
        self.assertEqual(render(q, ['0'], [1])['confidence'], 1)

class TokenBudgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from transformers import AutoTokenizer
        cls.tokenizer = AutoTokenizer.from_pretrained('/workspace/models/this-that-1.2', local_files_only=True)
    def test_exact_budget_and_one_token_over(self):
        body = RequestBody.model_validate({**BASE, 'state': ' hello' * 1000})
        built, keys = encode(self.tokenizer, body)
        length = len(built['ids'])
        self.assertEqual(encode(self.tokenizer, body, length)[0]['ids'], built['ids'])
        with self.assertRaises(APIError): encode(self.tokenizer, body, length - 1)
        self.assertGreater(len(built['ids']), 1000)
    def test_questions_and_criteria_count_toward_budget(self):
        body = RequestBody.model_validate({'state': 'hi', 'questions': {'x': {'type': 'choice', 'criteria': {'a': 'x ' * 32768}}}})
        with self.assertRaises(APIError): encode(self.tokenizer, body)
    def test_wide_options(self):
        body = RequestBody.model_validate({'state': 'hi', 'questions': {'x': {'type': 'choice', 'criteria': {str(i): None for i in range(255)}}}})
        built, keys = encode(self.tokenizer, body)
        self.assertEqual(built['n_options'], [255])
        self.assertEqual(len(keys[0]), 255)

if __name__ == '__main__': unittest.main()
