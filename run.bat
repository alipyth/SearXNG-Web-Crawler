@echo off
cls
echo ================================================================
echo                      SearXNG WEB CRAWLER
echo            Search - Crawl - Clean - Export - Corpus
echo ================================================================
echo  Developed by : Ali Jahani
echo  Telegram     : https://t.me/tarfandoonchannel
echo  Website      : https://jahaniwww.com
echo ================================================================
echo.
if not exist .env copy .env.example .env >nul
docker compose up -d --build
echo.
echo UI:      http://localhost:7860
echo SearXNG: http://localhost:8444
echo.
echo To see the branded container terminal/logs:
echo docker compose logs -f app
