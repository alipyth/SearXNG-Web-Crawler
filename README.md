# SearX Corpus Studio

Developed by **Ali Jahani**  
Telegram channel: https://t.me/tarfandoonchannel  
Website: https://jahaniwww.com

A Dockerized, local-first web research pipeline built on **SearXNG**.

Search the web, collect result URLs, crawl public pages, extract clean Markdown, archive everything as ZIP/JSON, search the extracted library from a browser UI, and build a deduplicated `.md` corpus for language-model training.

## What it does

```text
Browser UI
   ↓
SearXNG metasearch
   ↓
Unique result URLs
   ↓
Concurrent crawler
   ↓
Trafilatura / BeautifulSoup extraction
   ↓
Clean Markdown + metadata
   ↓
SQLite + FTS5 searchable library
   ↓
ZIP archive / training_corpus.md
```

### Features

- Bundled SearXNG using the official `searxng/searxng` Docker image.
- JSON search API enabled automatically.
- Best-effort collection of up to 100 results by default.
- URL normalization and duplicate-result removal.
- Concurrent crawling with retry/backoff.
- Main-content extraction with Trafilatura and a BeautifulSoup fallback.
- One Markdown file per crawled page.
- Metadata frontmatter: URL, title, author, site, publication date, etc.
- ZIP archives containing `results.json`, failed results, and Markdown files.
- Persistent SQLite database.
- SQLite FTS5 full-text search across extracted documents.
- Browser UI for search, job progress, library search, document reading, archives, and corpora.
- Corpus builder that removes frontmatter, images, HTML noise, very short documents, and exact duplicates.
- SSRF protection blocks local/private/reserved targets.
- Optional `robots.txt` respect enabled by default.
- CLI in addition to the browser UI.

> This project does **not** bypass CAPTCHA, paywalls, authentication, robots restrictions, or anti-bot/security controls. Search engines and destination websites can still rate-limit or refuse requests.

---

## Quick start

### Requirements

You only need:

- Docker Desktop / Docker Engine
- Docker Compose v2

You do **not** need to install Python or SearXNG manually when using Docker Compose.

### 1. Clone the repository

```bash
git clone https://github.com/YOUR_USERNAME/searx-corpus-studio.git
cd searx-corpus-studio
```

### 2. Create your environment file

Linux/macOS:

```bash
cp .env.example .env
```

Windows CMD:

```bat
copy .env.example .env
```

PowerShell:

```powershell
Copy-Item .env.example .env
```

### 3. Start everything

```bash
docker compose up -d --build
```

Open:

- **App UI:** http://localhost:7860
- **SearXNG:** http://localhost:8444
- **FastAPI docs:** http://localhost:7860/docs

Check status:

```bash
docker compose ps
```

View logs:

```bash
docker compose logs -f app
```

Stop:

```bash
docker compose down
```

---


## SearXNG JSON API configuration

The bundled `searxng/settings.yml` already enables JSON output, which is required by the crawler:

```yaml
use_default_settings: true

server:
  secret_key: "NzMpWbu8En8foDubz73JdFRx1VnNbSgm"
  image_proxy: true
  limiter: false
  public_instance: false

search:
  safe_search: 0
  formats:
    - html
    - json
```

The project is intended for local/private use. If you expose the SearXNG instance publicly, replace the bundled `secret_key` with your own strong random value and review the limiter/public-instance settings before deployment.

---

## First search

Open `http://localhost:7860`, enter a query such as:

```text
local LLM research
```

Choose the target result count and click **Search + Crawl**.

The app will:

1. Query SearXNG.
2. Walk through multiple SearXNG result pages.
3. Deduplicate normalized URLs.
4. Crawl public HTML pages concurrently.
5. Extract the main readable content.
6. Save Markdown under `data/sites/`.
7. Index the content in SQLite FTS5.
8. Generate a ZIP archive under `data/archives/`.

A target of `100` is best-effort. SearXNG engines can return fewer unique results, and some destination sites may reject crawlers.

---

## Data layout

All persistent user data is stored in `./data`:

```text
data/
├── library.db
├── sites/
│   ├── example.com/
│   │   └── article__abc123.md
│   └── another-site.org/
│       └── page__def456.md
├── archives/
│   └── my_query_20260913_120000.zip
└── corpora/
    └── my_query_20260913_120000_training_corpus.md
```

A generated ZIP looks like:

```text
results.json
failed.json                 # only when failures exist
sites/
  example.com/
    article__abc123.md
```

---

## Search your extracted data

The **Library** tab searches:

- page title
- domain
- full extracted Markdown content

The application uses SQLite FTS5 for fast local full-text search. If an unusual SQLite build lacks FTS5 query support, the application falls back to a basic `LIKE` search.

Click **Read** on any result to inspect the stored Markdown directly in the UI.

---

## Build an LLM training corpus

Open **Archives & Corpora**.

For an archive, click **Build corpus**.

The corpus builder:

- safely extracts the ZIP
- reads every `.md` file recursively
- strips YAML frontmatter
- removes Markdown images
- removes remaining HTML tags
- removes zero-width characters
- collapses excessive whitespace
- rejects very short documents
- removes exact normalized duplicates with SHA-256
- joins accepted documents with Markdown separators

The resulting file is saved under:

```text
data/corpora/*_training_corpus.md
```

You can download it from the UI.

---

## Configuration

Edit `.env`:

```env
APP_PORT=7860
SEARXNG_IMAGE=searxng/searxng:2026.9.11-ffe96f8a6
SEARXNG_PORT=8444
MAX_RESULTS=100
MAX_SEARCH_PAGES=20
CRAWL_WORKERS=6
RESPECT_ROBOTS_TXT=true
MIN_CONTENT_LENGTH=300
```

### `APP_PORT`

Host port for the browser UI and API.

### `SEARXNG_PORT`

Host port for the bundled SearXNG instance.

Inside Docker, the app talks to SearXNG using:

```text
http://searxng:8080
```

### `MAX_RESULTS`

Default target number of unique search results.

The UI currently allows 1–500 per job.

### `MAX_SEARCH_PAGES`

Maximum number of SearXNG pages queried while trying to reach the result target.

### `CRAWL_WORKERS`

Number of pages crawled concurrently.

Increase carefully. More workers can make destination sites rate-limit you faster.

### `RESPECT_ROBOTS_TXT`

Default:

```env
RESPECT_ROBOTS_TXT=true
```

Set to `false` only if you understand the implications and have permission for the target sites.

### `MIN_CONTENT_LENGTH`

Minimum cleaned document length accepted by the corpus builder.

---

## SearXNG configuration

The bundled config is:

```text
searxng/settings.yml
```

Important section:

```yaml
search:
  formats:
    - html
    - json
```

The `json` format is required because the Python application calls SearXNG's JSON Search API.

The bundled SearXNG is intended for local/private use. Before exposing it publicly, review SearXNG's deployment/security documentation and replace the example secret key.

---

## Use an existing SearXNG instance

The default Docker setup bundles SearXNG, which is the easiest path.

If you already run SearXNG elsewhere, ensure its JSON output is enabled:

```yaml
search:
  formats:
    - html
    - json
```

Then point the app's `SEARXNG_URL` environment variable at that instance. If the app runs inside Docker and your SearXNG is on the host, the hostname may need to be `host.docker.internal` rather than `localhost`.

Example:

```yaml
environment:
  SEARXNG_URL: http://host.docker.internal:8444
```

You can also remove/comment out the bundled `searxng` service if you no longer need it.

---

## CLI usage

For Docker users, run the CLI inside the app container.

### Search and crawl

```bash
docker compose exec app python -m app.cli search "artificial intelligence agents" --max-results 100
```

### Build corpus from an archive

```bash
docker compose exec app python -m app.cli corpus /data/archives/YOUR_ARCHIVE.zip
```

---

## Run locally without Docker

Docker is recommended because SearXNG is a separate service. If you want to run only the Python app locally:

```bash
python -m venv .venv
```

Windows:

```bat
.venv\Scripts\activate
```

Linux/macOS:

```bash
source .venv/bin/activate
```

Install:

```bash
pip install -e .
```

Set the SearXNG URL.

PowerShell example:

```powershell
$env:SEARXNG_URL="http://localhost:8444"
$env:DATA_DIR="$PWD/data"
uvicorn app.main:app --reload --port 7860
```

---

## API examples

### Start a search/crawl job

```bash
curl -X POST http://localhost:7860/api/search \
  -H "Content-Type: application/json" \
  -d '{"query":"local LLM research","max_results":100}'
```

Response:

```json
{
  "job_id": "..."
}
```

### Check a job

```bash
curl http://localhost:7860/api/jobs/JOB_ID
```

### Full-text search extracted documents

```bash
curl "http://localhost:7860/api/library?q=mixture%20of%20experts"
```

### Health

```bash
curl http://localhost:7860/api/health
```

---

## Safety and crawler behavior

The crawler includes basic protections that are important for a server-side URL fetcher:

- only `http` and `https` are accepted
- DNS targets are checked before fetching
- loopback/private/link-local/reserved IP targets are blocked
- redirects are validated again before following
- HTML download size is capped
- non-HTML content is skipped
- retries use exponential backoff for common transient errors
- `robots.txt` is respected by default

The project intentionally does not include CAPTCHA bypass, proxy rotation, authentication bypass, paywall bypass, or anti-bot evasion.

---

## Development / tests

Install development dependencies if needed:

```bash
pip install -e . pytest
pytest -q
```

Basic syntax check:

```bash
python -m compileall app
```

---

## Troubleshooting

### `403 Forbidden` from SearXNG JSON search

Check `searxng/settings.yml` and make sure:

```yaml
search:
  formats:
    - html
    - json
```

Then restart:

```bash
docker compose restart searxng
```

### App starts before SearXNG is ready

Wait a few seconds and submit the search again, or inspect:

```bash
docker compose logs -f searxng
```

### Fewer than 100 results

`100` is a target, not a guarantee. Results depend on enabled SearXNG engines, upstream rate limits, duplicate URLs, and the number of available result pages.

### Some crawl jobs fail

Common causes include:

- `403` / `429`
- JavaScript-only pages
- robots restrictions
- login/paywall pages
- non-HTML URLs
- connection timeout
- destination anti-bot systems

Failures are retained in the archive metadata rather than stopping the entire job.

---

## Repository structure

```text
.
├── app/
│   ├── main.py            # FastAPI + UI/API routes
│   ├── crawler.py         # SearXNG search + page crawler
│   ├── corpus.py          # corpus cleaner/builder
│   ├── storage.py         # SQLite + FTS5
│   ├── config.py
│   ├── cli.py
│   ├── templates/
│   │   └── index.html
│   └── static/
│       ├── app.js
│       └── style.css
├── searxng/
│   └── settings.yml
├── tests/
├── data/
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
├── requirements.txt
├── .env.example
└── README.md
```

---

## Updating SearXNG

Pull the current image and recreate the services:

```bash
docker compose pull searxng
docker compose up -d
```

For reproducible deployments, change `SEARXNG_IMAGE` in `.env` to the desired official SearXNG release tag.

---

## License

MIT for the code in this repository. SearXNG and third-party Python dependencies retain their own licenses.

## Persian quick start / راه‌اندازی سریع

اگر فقط می‌خواهی پروژه را اجرا کنی:

```bat
copy .env.example .env
docker compose up -d --build
```

بعد باز کن:

```text
http://localhost:7860
```

SearXNG هم خودکار روی این آدرس بالا می‌آید:

```text
http://localhost:8444
```

از تب **Search & Crawl** سرچ کن، از تب **Library** بین کل متن‌های استخراج‌شده جستجو کن، و از **Archives & Corpora** خروجی ZIP یا فایل یکپارچه `.md` برای دیتاست مدل زبانی بگیر.


## Upstream documentation

- SearXNG container installation: https://docs.searxng.org/admin/installation-docker
- SearXNG Search API: https://docs.searxng.org/dev/search_api
- Official SearXNG Docker image: https://hub.docker.com/r/searxng/searxng
