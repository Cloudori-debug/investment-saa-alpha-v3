# syntax=docker/dockerfile:1
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src
COPY app.py ./
COPY scripts ./scripts
COPY data ./data
COPY tests ./tests

RUN pip install --no-cache-dir -e ".[dev,ui,data]"

ENV PYTHONUNBUFFERED=1
EXPOSE 8501

CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501"]
