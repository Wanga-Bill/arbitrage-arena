# Dedicated Python Runtime Engine for Arbitrage Arena Blockchain Worker
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Explicit entry instruction running your on-chain listener daemon 24/7
CMD ["python", "watcher.py"]
