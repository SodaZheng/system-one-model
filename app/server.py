"""Single-model, bounded-queue TypeSafe-compatible HTTP service."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
import hmac
import io
import json
import logging
import os
import resource
import zlib
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from .protocol import APIError, MODEL, RequestBody, resolve_model

log = logging.getLogger('one-system-model')
BODY_LIMIT = 2 * 1024 * 1024


def error(status, code, message, detail=None):
    return JSONResponse(status_code=status, content={
        'detail': detail if detail is not None else {'code': code, 'message': message},
        'error': {'code': code, 'message': message, 'type': 'invalid_request_error' if status < 500 else 'server_error'}
    }, headers={'Retry-After': '5'} if status == 429 else None)


class BoundedBody:
    def __init__(self, app): self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope['method'] != 'POST':
            return await self.app(scope, receive, send)
        headers = dict(scope.get('headers', []))
        raw = bytearray()
        while True:
            msg = await receive()
            if msg['type'] == 'http.disconnect': return
            raw.extend(msg.get('body', b''))
            if len(raw) > BODY_LIMIT:
                return await error(413, 'body_too_large', 'Request body exceeds 2 MiB.')(scope, receive, send)
            if not msg.get('more_body', False): break
        encoding = headers.get(b'content-encoding', b'identity').decode().lower()
        try:
            if encoding == 'zstd':
                import zstandard
                with zstandard.ZstdDecompressor(max_window_size=16 * 1024 * 1024).stream_reader(io.BytesIO(raw), read_across_frames=True) as reader:
                    body = reader.read(BODY_LIMIT + 1)
            elif encoding in ('gzip', 'deflate'):
                decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS if encoding == 'gzip' else zlib.MAX_WBITS)
                body = decompressor.decompress(raw, BODY_LIMIT + 1)
                if len(body) <= BODY_LIMIT and not decompressor.eof:
                    raise ValueError('Incomplete compressed body')
                if decompressor.unused_data:
                    raise ValueError('Trailing compressed data')
            elif encoding in ('identity', ''): body = bytes(raw)
            else:
                return await error(415, 'unsupported_encoding', 'Use identity, zstd, gzip or deflate.')(scope, receive, send)
        except Exception:
            return await error(400, 'invalid_compression', 'Invalid or excessive compressed request body.')(scope, receive, send)
        if len(body) > BODY_LIMIT:
            return await error(413, 'body_too_large', 'Decompressed body exceeds 2 MiB.')(scope, receive, send)
        scope = dict(scope)
        scope['headers'] = [(k, v) for k, v in scope['headers'] if k not in (b'content-length', b'content-encoding')]
        scope['headers'].append((b'content-length', str(len(body)).encode()))
        delivered = False
        async def replay():
            nonlocal delivered
            if delivered: return await receive()
            delivered = True
            return {'type': 'http.request', 'body': body, 'more_body': False}
        return await self.app(scope, replay, send)


def create_app(runtime_factory=None):
    if runtime_factory is None:
        from .runtime import Runtime
        runtime_factory = Runtime

    @asynccontextmanager
    async def lifespan(app):
        app.state.api_key = os.getenv('API_KEY', '')
        if not app.state.api_key:
            raise RuntimeError('Set API_KEY (scripts/init_env.py creates a local key).')
        maximum = int(os.getenv('MAX_QUEUED_REQUESTS', '8'))
        if not 1 <= maximum <= 64: raise ValueError('MAX_QUEUED_REQUESTS must be 1..64')
        app.state.queue = asyncio.Queue(maxsize=maximum)
        app.state.busy = False
        pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='inference')
        loop = asyncio.get_running_loop()
        app.state.runtime = await loop.run_in_executor(pool, runtime_factory)
        async def worker():
            while True:
                item = await app.state.queue.get()
                if item is None:
                    app.state.queue.task_done()
                    return
                body, future = item
                try:
                    if future.cancelled(): continue
                    app.state.busy = True
                    result = await loop.run_in_executor(pool, app.state.runtime.predict, body)
                    if not future.done(): future.set_result(result)
                except Exception as exc:
                    if not future.done(): future.set_exception(exc)
                finally:
                    app.state.busy = False
                    app.state.queue.task_done()
        worker_task = asyncio.create_task(worker())
        try: yield
        finally:
            await app.state.queue.put(None)
            await worker_task
            pool.shutdown(wait=True)

    app = FastAPI(title='THIS/THAT 1.2 — TypeSafe text API', version='1.2.0', lifespan=lifespan)
    app.add_middleware(BoundedBody)
    app.add_middleware(CORSMiddleware, allow_origins=os.getenv('CORS_ORIGINS', '*').split(','),
                       allow_methods=['GET', 'POST', 'OPTIONS'], allow_headers=['*'])

    def authorize(request):
        supplied = request.headers.get('authorization', '')
        expected = 'Bearer ' + app.state.api_key
        if not hmac.compare_digest(supplied.encode(), expected.encode()):
            raise APIError(401, 'invalid_api_key', 'A valid local Bearer API key is required.')

    @app.exception_handler(APIError)
    async def api_error(request, exc): return error(exc.status, exc.code, exc.message)

    @app.get('/health')
    @app.get('/healthz', include_in_schema=False)
    def health():
        runtime = app.state.runtime
        return {'status': 'ok', 'model': MODEL, 'revision': 'c4d1c30b8d512d278726de439b8cc81fccc70c8f',
                'device': 'cpu', 'dtype': 'float32', 'offline': True, 'modalities': ['text'],
                'max_context_tokens': runtime.max_tokens, 'threads': runtime.threads,
                'prefill_chunk_size': runtime.chunk_size, 'busy': app.state.busy,
                'queued_requests': app.state.queue.qsize(),
                'max_queued_requests': app.state.queue.maxsize,
                'completed_requests': runtime.completed_requests,
                'process_peak_rss_bytes': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024}

    @app.get('/v1/models')
    @app.get('/models', include_in_schema=False)
    @app.get('/v1/v1/models', include_in_schema=False)
    async def models(request: Request):
        authorize(request)
        return {'models': [{'name': name, 'release_date': '2026-09-23',
                            'description': 'Local THIS/THAT 1.2 CPU, text only, 32768 total tokens; Jev names are compatibility aliases.'}
                           for name in (MODEL, 'thisthat', 'jev-latest', 'jev-preview')]}

    @app.post('/v1/systemone')
    @app.post('/systemone', include_in_schema=False)
    @app.post('/v1/v1/systemone', include_in_schema=False)
    async def systemone(request: Request):
        authorize(request)
        if not request.headers.get('content-type', '').split(';')[0].strip() == 'application/json':
            return error(415, 'unsupported_media_type', 'Text requests must use application/json; image multipart requests are unsupported.')
        try:
            raw = await request.json()
            if isinstance(raw, dict):
                if raw.get('assets'):
                    return error(422, 'unsupported_modality', 'THIS/THAT 1.2 supports text only; images are unsupported.')
                if isinstance(raw.get('questions'), dict) and any(isinstance(q, dict) and q.get('type') == 'box' for q in raw['questions'].values()):
                    return error(422, 'unsupported_modality', 'THIS/THAT 1.2 cannot answer Box questions.')
            body = RequestBody.model_validate(raw)
            resolve_model(body.model)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return error(400, 'invalid_json', 'Invalid JSON request.')
        except ValidationError as exc:
            detail = [{'loc': ['body', *e['loc']], 'msg': e['msg'], 'type': e['type']} for e in exc.errors(include_input=False)]
            return error(422, 'validation_error', 'Invalid System One request.', detail)
        future = asyncio.get_running_loop().create_future()
        try: app.state.queue.put_nowait((body, future))
        except asyncio.QueueFull:
            return error(429, 'queue_full', 'Inference queue is full; retry later.')
        try:
            return await future
        except asyncio.CancelledError:
            future.cancel()
            raise
        except APIError: raise
        except Exception:
            log.exception('Inference failed')
            return error(500, 'inference_failed', 'Local inference failed; see server logs.')

    return app

app = create_app()
