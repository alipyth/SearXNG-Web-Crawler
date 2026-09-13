#!/usr/bin/env sh
set -eu
cat <<'EOF'
================================================================
                     SearXNG WEB CRAWLER
           Search - Crawl - Clean - Export - Corpus
================================================================
 Developed by : Ali Jahani
 Telegram     : https://t.me/tarfandoonchannel
 Website      : https://jahaniwww.com
================================================================
EOF
[ -f .env ] || cp .env.example .env
docker compose up -d --build
printf '\nUI:      http://localhost:7860\nSearXNG: http://localhost:8444\n\nRun: docker compose logs -f app\n'
