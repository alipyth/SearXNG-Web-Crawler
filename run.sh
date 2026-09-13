#!/usr/bin/env sh
set -eu
[ -f .env ] || cp .env.example .env
docker compose up -d --build
printf '\nSearX Corpus Studio: http://localhost:7860\nSearXNG:             http://localhost:8444\n'
