FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps for pdfplumber/pymupdf and asyncpg builds.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY src ./src
RUN pip install --upgrade pip && pip install .

COPY alembic.ini ./
COPY alembic ./alembic

RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --create-home --shell /usr/sbin/nologin app \
    && mkdir -p /app/.storage /app/.qdrant \
    && chown -R app:app /app

USER app

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.getenv('PORT', '8000') + '/health', timeout=3)" || exit 1

# Apply the migration chain before serving. Without this the database has no
# tables and every route that touches it raises an unhandled exception, which
# reaches the browser as a bare 500 with no CORS headers. Fail fast: if the
# migration fails the container must not start, so the error is visible in the
# deploy log instead of being masked as a runtime 500.
CMD alembic upgrade head && exec uvicorn tender_intel.api.app:app --host 0.0.0.0 --port ${PORT:-8000}
