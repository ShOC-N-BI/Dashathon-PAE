FROM python:3.11-slim

WORKDIR /app

# System dependencies for psycopg2
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all application code
COPY ai/              ./ai/
COPY client/          ./client/
COPY irc/             ./irc/
COPY output/          ./output/
COPY pipeline/        ./pipeline/
COPY schemas/         ./schemas/
COPY sse/             ./sse/
COPY tests/           ./tests/
COPY data/            ./data/
COPY pae_config.py    .
COPY config_server.py .
COPY main.py          .

RUN mkdir -p /app/logs

ENV PYTHONUNBUFFERED=1

# Default command — overridden per service in docker-compose.yml
CMD ["python", "main.py"]
