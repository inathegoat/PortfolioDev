# Second Brain — Dockerfile
# ===========================
# Multi-stage build: builder + runtime
#
# Build:  docker build -t second-brain .
# Run:    docker run -p 8000:8000 -v $(pwd)/data:/app/data second-brain
# API:    docker run -p 8000:8000 -v $(pwd)/data:/app/data second-brain api
#
# Requires Ollama running on the host (or use --network host).

# ── Stage 1: Builder ─────────────────────────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /app

# Install build dependencies
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# Copy dependency files
COPY pyproject.toml requirements.txt ./

# Install dependencies into a venv
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir -r requirements.txt

# ── Stage 2: Runtime ─────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

WORKDIR /app

# Copy virtualenv from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application code
COPY config/ ./config/
COPY src/    ./src/
COPY main.py ./

# Create data directories
RUN mkdir -p data/raw data/processed data/db data/exports data/notes logs

# Download embedding model at build time (cached)
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')" || true

# Expose API port
EXPOSE 8000

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/api/status', timeout=5)" || exit 1

# Default: CLI
ENTRYPOINT ["python", "main.py"]
CMD ["--help"]
