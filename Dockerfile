# syntax=docker/dockerfile:1
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies required by SQLite and build tools.
RUN apt-get update \
    && apt-get install --no-install-recommends -y build-essential libsqlite3-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Expose Flask default port
EXPOSE 5000

# Initialize the database when the container starts for the first time.
RUN python db/init_db.py

CMD ["flask", "--app", "app", "run", "--host", "0.0.0.0", "--port", "5000"]
