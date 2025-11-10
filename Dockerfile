# AIDEFEND MCP Service Dockerfile
# Multi-stage build for security and minimal image size

# Stage 1: Build stage
FROM python:3.11-slim as builder

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

# Create non-root user for security
RUN groupadd -r aidefend && useradd -r -g aidefend aidefend

# Set working directory
WORKDIR /app

# Copy Python dependencies from builder
COPY --from=builder /root/.local /home/aidefend/.local

# Copy application code
COPY app/ ./app/

# Copy LICENSE for open source compliance
COPY LICENSE /app/LICENSE

# Create data directory and set permissions
RUN mkdir -p /app/data /app/data/logs /app/data/raw_content && \
    chown -R aidefend:aidefend /app

# Switch to non-root user
USER aidefend

# Set environment variables
ENV PATH=/home/aidefend/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health').raise_for_status()"

# Run application
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
