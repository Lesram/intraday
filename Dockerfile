# Multi-stage Dockerfile for production deployment with security hardening
# BRANCH 2.12 - Deploy Readiness + Security Enhancements

# Build arguments
ARG BUILD_DATE
ARG VCS_REF
ARG VERSION=1.0.0

# Metadata
LABEL maintainer="Trading Platform Team <dev@trading-platform.com>"
LABEL org.opencontainers.image.title="Algorithmic Trading Platform"
LABEL org.opencontainers.image.version=${VERSION}
LABEL org.opencontainers.image.created=${BUILD_DATE}
LABEL org.opencontainers.image.revision=${VCS_REF}

#################################################################
# Builder Stage - Install dependencies and build wheels
#################################################################
FROM python:3.11-slim AS builder

# Build arguments for Python optimization
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libpq-dev \
    python3-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy dependency files
COPY requirements.txt requirements.lock ./

# Install dependencies into virtual environment
# Use requirements.lock for exact reproducible builds
RUN pip install --upgrade pip wheel setuptools && \
    pip install -r requirements.lock

#################################################################
# Runtime Stage - Minimal production image
#################################################################
FROM python:3.11-slim AS runtime

# Runtime environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    LANG=C.UTF-8 \
    PATH="/opt/venv/bin:$PATH"

# Install minimal runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create non-root user for security
RUN useradd -u 10001 -r -g 0 -d /app -s /sbin/nologin -c "Application User" appuser

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Create application directory structure
RUN mkdir -p /app /app/logs /app/tmp && \
    chown -R appuser:root /app && \
    chmod -R g=u /app

# Set working directory
WORKDIR /app

# Copy application code
COPY --chown=appuser:root . .

# Switch to non-root user
USER appuser

# Create necessary directories with proper permissions
RUN mkdir -p logs tmp data

# Health check using the application's health endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/healthz || exit 1

# Expose application port
EXPOSE 8000

# Application entrypoint with uvloop for better performance
# Single worker since we use async/await with background tasks
CMD ["uvicorn", "backend.api.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1", \
     "--loop", "uvloop", \
     "--access-log", \
     "--log-config", "/app/logging_config.yaml"]
