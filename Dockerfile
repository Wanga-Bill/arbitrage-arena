FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (build-essential, libpq-dev are needed for compiling psycopg2)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Install dependencies including psycopg2-binary, fastapi, uvicorn
RUN pip install --no-cache-dir -r requirements.txt psycopg2-binary fastapi uvicorn

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
