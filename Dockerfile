# One service: the FastAPI backend serves the API and the built interface.
# Works on Render, Hugging Face Spaces (Docker) or any container host.

FROM node:22-slim AS interface
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install -r backend/requirements.txt
COPY backend/ backend/
COPY ml/models/ ml/models/
COPY ml/data/processed/ ml/data/processed/
COPY ml/reports/ ml/reports/
COPY --from=interface /app/frontend/dist frontend/dist

# Hosted demo defaults; every value can be overridden in the host's settings.
ENV DATA_DIR=/tmp/agentforge-data \
    STEP_DELAY_SECONDS=0.4 \
    DEMO_AUDITS_PER_HOUR=8 \
    PORT=7860
WORKDIR /app/backend
EXPOSE 7860
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
