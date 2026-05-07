FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot/ ./bot/
COPY .env.example .env

RUN mkdir -p /app/storage /app/data /app/logs

VOLUME ["/app/storage", "/app/data", "/app/logs"]

CMD ["python", "-m", "bot.app"]
