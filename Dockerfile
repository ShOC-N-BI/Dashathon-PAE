# ── Build stage ───────────────────────────────────────────────────────────
FROM python:3.11-slim AS base

# Set working directory
WORKDIR /app

# Install system dependencies needed for psycopg2
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Application ───────────────────────────────────────────────────────────
FROM base AS app

WORKDIR /app

# Copy all application code
COPY ai/           ./ai/
COPY client/       ./client/
COPY irc/          ./irc/
COPY output/       ./output/
COPY pipeline/     ./pipeline/
COPY schemas/      ./schemas/
COPY data/         ./data/
COPY config.py     .
COPY main.py       .

# Log output is written here — mount a volume to persist it
RUN mkdir -p /app/logs

# Environment variables are injected at runtime via .env or docker-compose
ENV PYTHONUNBUFFERED=1

CMD ["python", "main.py"]
