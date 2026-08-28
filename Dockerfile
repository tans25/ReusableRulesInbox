# ---------- Stage 1: build a slim Python image ----------
FROM python:3.12-slim AS base

# Prevent Python from writing .pyc files and enable unbuffered stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first (layer-cached unless requirements.txt changes)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code and data
COPY app/ ./app/
COPY data/ ./data/
COPY static/ ./static/

# Render injects PORT; default to 10000 for local testing
ENV PORT=10000

EXPOSE ${PORT}

# Run with uvicorn — bind to 0.0.0.0 so Docker/Render can reach it
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
