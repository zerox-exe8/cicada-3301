# =========================================================================
# Multi-Stage Minimal Production Dockerfile for Kyro Engine & KyroLink
# Highly Portable: Runs on Railway, Render, Hetzner, AWS, Fly.io, Kubernetes
# =========================================================================

# Stage 1: Build Dependencies
FROM python:3.13-slim AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# Stage 2: Final Minimal Runtime Image
FROM python:3.13-slim

WORKDIR /app

# Install runtime system packages: FFmpeg and libopus for audio encoding
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libopus0 \
    ca-certificates \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

# Create non-root system user for security
RUN groupadd -r kyro && useradd -r -g kyro -d /app kyro

# Copy application source code
COPY . /app

# Ensure entrypoint is executable and transfer ownership
RUN chmod +x /app/entrypoint.sh && chown -R kyro:kyro /app

USER kyro

# Environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000 \
    HOST=0.0.0.0

# Expose dynamic port
EXPOSE 8000

# Docker healthcheck
HEALTHCHECK --interval=15s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/health || exit 1

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["python", "main.py"]
