FROM python:3.12-slim-bookworm AS dependencies
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    USE_TF=0 TOKENIZERS_PARALLELISM=false
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.lock /app/requirements.lock
RUN python -m pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu \
    -r /app/requirements.lock && python -m pip check

FROM dependencies AS runtime
COPY models/this-that-1.2/ /app/models/this-that-1.2/
COPY app/ /app/app/
COPY vendor/this-that-model/thisthat/ /app/thisthat/
COPY scripts/verify_model.py /app/scripts/verify_model.py
COPY vendor/this-that-model/LICENSE /app/THISTHAT_LICENSE
RUN python /app/scripts/verify_model.py /app/models/this-that-1.2
ENV MODEL_PATH=/app/models/this-that-1.2 THREADS=8 PREFILL_CHUNK_SIZE=512 \
    MAX_CONTEXT_TOKENS=32768 MAX_QUEUED_REQUESTS=8 \
    HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 HF_HUB_DISABLE_TELEMETRY=1 HF_HOME=/tmp/huggingface \
    OMP_NUM_THREADS=8 MKL_NUM_THREADS=8 MALLOC_ARENA_MAX=2
USER 10001:10001
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=180s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=3).read()"]
CMD ["python", "-m", "uvicorn", "app.server:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1", "--no-access-log"]
