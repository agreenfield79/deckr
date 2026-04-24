FROM python:3.11-slim

WORKDIR /app

# System deps for psycopg2-binary, pymupdf, and chromadb
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Ensure data/ directory exists for SQLite and ChromaDB
RUN mkdir -p data

EXPOSE 8000

# Cloud Run injects PORT env var (default 8080). We default to 8000 for local dev.
# Use shell form so ${PORT:-8000} is expanded at runtime.
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
