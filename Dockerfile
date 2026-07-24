# AIDEFEND MCP Service Dockerfile
# Multi-stage build for security and minimal image size

# Stage 1: Build stage
FROM python:3.11-slim AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /build

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 2: Runtime stage
FROM python:3.11-slim

# Install Node.js for the secure JavaScript AST parser. Acorn is vendored below,
# so npm and node_modules are not needed in the runtime image. ONNX Runtime's
# Linux wheel requires the GNU OpenMP runtime, which is not part of the slim
# Python base image.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    nodejs \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN groupadd -r aidefend && useradd -r -g aidefend aidefend

# Set working directory
WORKDIR /app

# Copy Python dependencies from builder
COPY --from=builder --chown=aidefend:aidefend /root/.local /home/aidefend/.local

# Copy application code
COPY app/ ./app/
COPY __main__.py ./
COPY mcp_server.py ./
COPY parse_js_module.mjs ./
# The parser imports the pinned, vendored Acorn module directly. Keeping it in
# the image avoids a runtime dependency on node_modules or an npm registry.
COPY vendor/ ./vendor/

# Copy LICENSE for open source compliance
COPY LICENSE /app/LICENSE
COPY THIRD_PARTY_CONTENT.md /app/THIRD_PARTY_CONTENT.md

# Create data directory and set permissions
RUN mkdir -p /app/data /app/data/logs /app/data/raw_content /app/data/models && \
    chown -R aidefend:aidefend /app

# Make the copied user-site dependencies and a writable home deterministic for
# both the build-time non-root smoke test and the final runtime.
ENV HOME=/home/aidefend \
    PATH=/home/aidefend/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Switch to non-root user
USER aidefend

# Fail the image build if the distro Node.js is below the documented floor, the
# vendored parser cannot load, Python dependencies are inconsistent, or a native
# runtime library (notably ONNX/OpenMP) is missing. These checks do not download
# the embedding model or contact the framework source.
RUN node -e 'if (Number(process.versions.node.split(String.fromCharCode(46))[0]) < 18) process.exit(1)' && \
    node --check parse_js_module.mjs && \
    node vendor/acorn.mjs && \
    python -m pip check && \
    python -c 'import app.main, fastembed, lancedb, mcp_server, onnxruntime, pyarrow'

# Set environment variables
# API_HOST=0.0.0.0 is REQUIRED inside a container (published ports can't reach a loopback
# bind). Because the app launches uvicorn from settings.API_HOST (see __main__.py -> app.cli),
# the security guard in app/config.py now sees the real bind address: a plain
# `docker run` with the default AUTH_MODE=no_auth is refused (fail-closed) instead of
# silently exposing an unauthenticated service. Set AUTH_MODE=api_key + AIDEFEND_API_KEY
# (as docker-compose.yml does) to run.
# MODEL_CACHE_DIR points the embedding model cache at the persisted /app/data volume so the
# ~280MB model is downloaded once, not on every container recreate.
ENV API_HOST=0.0.0.0 \
    DATA_PATH=/app/data \
    MODEL_CACHE_DIR=/app/data/models

# Expose port
EXPOSE 8000

# Health check. A first-run model download plus framework sync is documented as
# taking up to 15 minutes, so readiness must not expire before that upper bound.
HEALTHCHECK --interval=30s --timeout=10s --start-period=900s --retries=3 \
    CMD python -c "import os,httpx; port=os.environ.get('API_PORT','8000'); r=httpx.get('http://localhost:'+port+'/health', timeout=5.0); r.raise_for_status(); c=r.json().get('checks', {}); assert c.get('database') and c.get('embedding_model')"

# Run application via the entry point so uvicorn binds settings.API_HOST/API_PORT and the
# no-auth-on-0.0.0.0 security guard governs the actual socket (see app/config.py).
CMD ["python", "__main__.py", "--api"]
