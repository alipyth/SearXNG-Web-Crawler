@echo off
if not exist .env copy .env.example .env >nul
docker compose up -d --build
echo.
echo SearX Corpus Studio: http://localhost:7860
echo SearXNG:             http://localhost:8444
