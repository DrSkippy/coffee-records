# Stage 1: Build React frontend
FROM node:20-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Python runtime
FROM python:3.12-slim AS runtime

# Install Poetry
RUN pip install --no-cache-dir poetry==1.8.3

WORKDIR /app

# Install system dependencies required by psycopg2-binary
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files first for layer caching
COPY pyproject.toml poetry.lock* ./

# Install Python dependencies (no dev)
RUN poetry config virtualenvs.create false \
    && poetry install --only main --no-root --no-interaction --no-ansi

# Copy application code
COPY coffee_records/ ./coffee_records/
COPY config.yaml ./

# Copy built frontend into Flask static directory
COPY --from=frontend-build /app/frontend/dist/ ./coffee_records/static/

EXPOSE 5000

CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "coffee_records:create_app()"]
