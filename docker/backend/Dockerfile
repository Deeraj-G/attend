# Backend dev container: FastAPI with autoreload, calling Nimble/BFL directly
# and the local model servers (see docker-compose.yml) over HTTP.
FROM python:3.13-slim

WORKDIR /app

# Core deps only: the models run in the lfm/lfm-audio containers, so no torch here.
COPY requirements-core.txt .
RUN pip install --no-cache-dir -r requirements-core.txt

COPY backend ./backend

EXPOSE 8000
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
