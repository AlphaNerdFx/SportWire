# --- Base Image ---
FROM python:3.10-slim

# Install system-level dependencies for asyncpg and pgvector C extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy dependency manifest first to leverage Docker layer caching
COPY requirements.txt .

# Install Python dependencies
# Note: logging, uuid, asyncio are stdlib — pip will warn and skip them safely
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy full project source
COPY . .

# Default: run the ingestion pipeline entrypoint
CMD ["python", "ingestion/run_ingestion.py"]
