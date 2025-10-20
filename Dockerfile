# MQTT to Telegram Rankings Bot - Dockerfile
# Multi-stage build for optimized image size

FROM python:3.11-slim as base

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install hummingbot-api-client from GitHub
RUN pip install --no-cache-dir git+https://github.com/hummingbot/hummingbot-api-client.git

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p logs data

# Run as non-root user for security
RUN useradd -m -u 1000 botuser && \
    chown -R botuser:botuser /app

USER botuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import os; os.path.exists('mqtt_telegram_execution_bot.log')" || exit 1

# Default command
CMD ["python", "main_execution_bot.py"]
