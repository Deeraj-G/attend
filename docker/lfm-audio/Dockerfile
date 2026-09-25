# Local server for LFM2.5-Audio-1.5B (STT + TTS) via the `liquid-audio` package.
# CPU by default; swap in a CUDA-enabled torch build for GPU.
FROM python:3.13-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py .

ENV LFM_AUDIO_MODEL_PATH=LiquidAI/LFM2.5-Audio-1.5B
EXPOSE 8090
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8090"]
