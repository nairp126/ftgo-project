# Multi-stage production Dockerfile
# Supports Requirement 14.6

# ---- Build Stage ----
FROM python:3.12-slim AS builder

WORKDIR /build

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---- Production Stage ----
FROM python:3.12-slim

WORKDIR /app

# Copy installed packages
COPY --from=builder /install /usr/local
RUN pip install --no-cache-dir setuptools

# Non-root user
RUN useradd --create-home appuser

# Copy application code
COPY --chown=appuser:appuser app/ ./app/
COPY --chown=appuser:appuser alembic.ini* ./
COPY --chown=appuser:appuser run.py .

# Copy migrations directory only if it exists (R2-7)
# Use a wildcard so the build doesn't fail if it's missing
COPY --chown=appuser:appuser migration[s]/ ./migrations/

USER appuser

# Environment defaults
ENV ENVIRONMENT=production \
    HOST=0.0.0.0 \
    PORT=8000 \
    LOG_LEVEL=INFO \
    LOG_FORMAT=json \
    PYTHONPATH=/app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

# Gunicorn with Uvicorn workers
CMD ["gunicorn", "app.main:app", \
    "-k", "uvicorn.workers.UvicornWorker", \
    "-w", "4", \
    "-b", "0.0.0.0:8000", \
    "--access-logfile", "-", \
    "--error-logfile", "-"]