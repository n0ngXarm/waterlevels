FROM python:3.12-slim

WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Asia/Bangkok

# Install system dependencies & timezone
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    tzdata \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code, data, and scripts
COPY . .

# Ensure data directory exists
RUN mkdir -p /app/data

# Define volume for persistent data
VOLUME ["/app/data"]

# Docker Healthcheck: runs every 60s
HEALTHCHECK --interval=60s --timeout=15s --start-period=20s --retries=3 \
    CMD python healthcheck.py

# Default entrypoint runs both background monitor and interactive bot
CMD ["python", "main.py", "run"]
