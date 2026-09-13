FROM python:3.12-slim

LABEL org.opencontainers.image.title="SearX Corpus Studio" \
      org.opencontainers.image.authors="Ali Jahani" \
      org.opencontainers.image.url="https://jahaniwww.com" \
      org.opencontainers.image.documentation="https://t.me/tarfandoonchannel" \
      com.alijahani.telegram="https://t.me/tarfandoonchannel" \
      com.alijahani.website="https://jahaniwww.com"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app

RUN mkdir -p /data/sites /data/archives /data/corpora
ENV DATA_DIR=/data

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
