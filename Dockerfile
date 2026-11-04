# =====================================================================
# Production Dockerfile for LeadGen & Booking Telegram Bot
# Base: Python 3.11 Slim (Debian-based minimal runtime)
# =====================================================================

FROM python:3.11-slim AS runtime

# Prevent Python from writing .pyc files to disk and disable output buffering
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Set standard working directory
WORKDIR /app

# Create dedicated non-root user and group for safe container execution
RUN groupadd --system --gid 10001 botuser && \
    useradd --system --uid 10001 --gid botuser --create-home --home-dir /home/botuser botuser

# Install Python package dependencies first (layer caching optimization)
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY . /app/

# Create /app/data directory for persistent SQLite storage and ensure botuser ownership
RUN mkdir -p /app/data && \
    chown -R botuser:botuser /app /home/botuser

# Switch to unprivileged runtime user
USER botuser

# Set entrypoint command to launch the bot
CMD ["python", "bot.py"]
