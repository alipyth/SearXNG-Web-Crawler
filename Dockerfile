FROM python:3.12-slim

LABEL org.opencontainers.image.title="SearXNG Web Crawler" \
      org.opencontainers.image.description="SearXNG-powered web search, crawling, Markdown extraction and LLM corpus builder" \
      org.opencontainers.image.authors="Ali Jahani" \
      org.opencontainers.image.url="https://jahaniwww.com" \
      org.opencontainers.image.source="https://github.com/alipyth/SearXNG-Web-Crawler" \
      org.opencontainers.image.documentation="https://github.com/alipyth/SearXNG-Web-Crawler#readme" \
      com.alijahani.telegram="https://t.me/tarfandoonchannel" \
      com.alijahani.website="https://jahaniwww.com"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY docker-entrypoint.sh /usr/local/bin/searxng-web-crawler-entrypoint
RUN chmod +x /usr/local/bin/searxng-web-crawler-entrypoint && mkdir -p /data/sites /data/archives /data/corpora

ENV DATA_DIR=/data
EXPOSE 8000
ENTRYPOINT ["searxng-web-crawler-entrypoint"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
