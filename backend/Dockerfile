FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Create non-root user and persistent data directory
RUN useradd -u 10001 -m -s /bin/bash appuser && \
    mkdir -p /app/data && \
    chmod 777 /app/data && \
    chown -R appuser:appuser /app

# Cache dependency layer
COPY pyproject.toml ./
RUN mkdir -p app && touch app/__init__.py && \
    pip install --no-cache-dir . && \
    rm -rf app

# Copy application source code and migrations
COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app

# Install the application itself non-editable
RUN pip install --no-cache-dir --no-deps . && \
    chown -R appuser:appuser /app

USER appuser

EXPOSE 8000
