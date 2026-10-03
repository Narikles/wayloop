# --- 1. Interface web -------------------------------------------------------
FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# --- 2. Application -----------------------------------------------------------
FROM python:3.13-slim
# Base SQLite par défaut dans /app/data (seul dossier accessible en écriture à l'utilisateur wayloop) ;
# docker-compose et les hébergeurs avec PostgreSQL la remplacent par DATABASE_URL.
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 STATIC_DIR=/app/static \
    DATABASE_URL=sqlite:////app/data/wayloop.db
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./
COPY --from=web /web/dist /app/static
RUN useradd --system --uid 1000 wayloop && mkdir -p /app/data/files && chown -R wayloop /app/data
USER wayloop
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python -c "import os,urllib.request;urllib.request.urlopen('http://localhost:%s/api/health' % os.environ.get('PORT', '8000'))"
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
