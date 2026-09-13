# SearXNG Web Crawler

**Search → Crawl → Clean → Export → Build LLM Corpora**

A Dockerized, local-first web data collection toolkit powered by **SearXNG**. Search the web, collect and deduplicate URLs, crawl public HTML pages, extract readable Markdown, search the collected library locally, export datasets as **JSON / CSV / Markdown**, and build a clean book-like corpus for language-model training.

> Developed by **Ali Jahani**  
> Telegram: https://t.me/tarfandoonchannel  
> Website: https://jahaniwww.com

## Highlights

- Bundled **SearXNG** in Docker — no separate SearXNG installation required.
- SearXNG JSON API preconfigured and enabled.
- Request from **1 up to 10,000 results** per search job.
- Best-effort multi-page SearXNG collection with URL normalization and deduplication.
- Concurrent public-web crawling with retry/backoff.
- Readable main-content extraction with **Trafilatura** and a BeautifulSoup fallback.
- Persistent Markdown files per crawled page.
- SQLite database with **FTS5 full-text search**.
- Browser UI for search, crawl progress, local library search, exports, and corpus building.
- Raw search exports in **ZIP, JSON, CSV, and Markdown**.
- Clean LLM corpus exports in **Markdown, JSON, and CSV**.
- Book-mode corpus cleaning removes frontmatter, images, HTML, link destinations, raw URLs, short pages, and exact duplicates.
- Delete controls for **Search Jobs**, **Library Documents**, **Archives**, and **Corpora**.
- SSRF protection blocks private/local/reserved network targets.
- `robots.txt` respect is enabled by default.
- Branded Docker startup logs and OCI image labels.

## Architecture

```text
Browser UI
   ↓
FastAPI app
   ↓
SearXNG
   ↓
Unique result URLs
   ↓
Concurrent crawler
   ↓
Trafilatura / BeautifulSoup
   ↓
Markdown + metadata
   ↓
SQLite + FTS5
   ↓
ZIP / JSON / CSV / MD
   ↓
Clean LLM corpus: MD / JSON / CSV
```

## Quick start

### Requirements

- Docker Desktop / Docker Engine
- Docker Compose v2

No local Python or SearXNG installation is required when using Docker.

### 1. Clone

```bash
git clone https://github.com/alipyth/SearXNG-Web-Crawler.git
cd SearXNG-Web-Crawler
```

### 2. Create `.env`

Windows CMD:

```bat
copy .env.example .env
```

PowerShell:

```powershell
Copy-Item .env.example .env
```

Linux/macOS:

```bash
cp .env.example .env
```

### 3. Run

```bash
docker compose up -d --build
```

Or on Windows:

```bat
run.bat
```

Open:

- UI: http://localhost:7860
- SearXNG: http://localhost:8444
- FastAPI docs: http://localhost:7860/docs

Watch the branded application terminal/logs:

```bash
docker compose logs -f app
```

## SearXNG configuration

The repository already contains `searxng/settings.yml` with JSON output enabled:

```yaml
use_default_settings: true

general:
  instance_name: "SearXNG Web Crawler"

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

For a public deployment, replace the bundled `secret_key` and review SearXNG security/limiter settings. The default setup is intended for local/private use.

## Search limits

The UI and API accept up to:

```text
10,000 requested results per job
```

This is a **target, not a guarantee**. Actual result count depends on enabled SearXNG engines, upstream pagination, duplicate URLs, engine rate limits, and available search results.

Large jobs can take significant time, bandwidth, disk space, and database space. Increase crawler concurrency carefully.

## Raw search exports

Every completed search creates four direct exports under `data/archives/`:

```text
my_query_20260913_230000.zip
my_query_20260913_230000.json
my_query_20260913_230000.csv
my_query_20260913_230000.md
```

The ZIP also contains:

```text
results.json
results.csv
collection.md
failed.json        # only if failures exist
sites/
  example.com/
    article__abc123.md
```

The JSON and CSV exports include extracted Markdown content and useful result/crawl metadata.

## Clean book-mode corpus for LLM training

Open **Archives & Corpora** and click **Build clean corpus**.

The cleaner:

- removes YAML frontmatter
- removes images
- converts Markdown hyperlinks to plain visible text
- removes raw `http://`, `https://`, and `www.` URLs
- removes HTML tags
- removes source/link-only lines
- removes zero-width characters
- collapses excessive whitespace
- ignores very short pages
- removes exact normalized duplicates
- keeps useful headings, paragraphs, lists, tables, and code-like text where possible

It creates three downloadable training formats:

```text
*_clean_corpus.md
*_clean_corpus.json
*_clean_corpus.csv
```

The Markdown version is intentionally book-like and does not include source URLs or frontmatter by default.

## Local Library

Every successfully crawled page is indexed in SQLite FTS5. The **Library** tab can search:

- title
- domain
- full extracted Markdown

Each document can be opened or deleted from the UI.

## Delete controls

The UI supports deletion from all major sections:

- **Search & Crawl** → delete a search job from history
- **Library** → delete a document and its stored Markdown file
- **Archives** → delete ZIP/JSON/CSV/MD exports for a search
- **Corpora** → delete MD/JSON/CSV versions of a clean corpus

## Persistent data

```text
data/
├── library.db
├── sites/
├── archives/
└── corpora/
```

The `data/` directory is ignored by Git except for placeholder files, so crawled datasets are not accidentally committed.

## Configuration

`.env.example`:

```env
SEARXNG_IMAGE=searxng/searxng:latest
APP_PORT=7860
SEARXNG_PORT=8444
MAX_RESULTS=100
MAX_RESULTS_LIMIT=10000
MAX_SEARCH_PAGES=2000
CRAWL_WORKERS=6
RESPECT_ROBOTS_TXT=true
MIN_CONTENT_LENGTH=300
```

### Important variables

`MAX_RESULTS_LIMIT=10000` controls the largest value accepted by the UI/API.

`MAX_SEARCH_PAGES=2000` is the hard ceiling for SearXNG pagination attempts. The collector stops earlier after repeated pages with no new unique URLs.

`CRAWL_WORKERS=6` controls concurrent page downloads. Raising it can increase speed but can also increase resource usage and trigger rate limits sooner.

`RESPECT_ROBOTS_TXT=true` is the recommended default.

## CLI

Search and crawl:

```bash
docker compose exec app python -m app.cli search "local LLM research" --max-results 500
```

Build clean MD/JSON/CSV corpora from an existing generated ZIP:

```bash
docker compose exec app python -m app.cli corpus /data/archives/my_query_20260913_230000.zip
```

## Safety and responsible use

This project does **not** bypass CAPTCHAs, authentication, paywalls, access controls, robots restrictions, or anti-bot systems. Destination websites and upstream search engines can rate-limit or refuse requests. Use the project only where you are authorized to collect and process the content, and respect applicable site terms and laws.

## Docker metadata

The Docker image/container includes author labels for:

```text
Developed by : Ali Jahani
Telegram     : https://t.me/tarfandoonchannel
Website      : https://jahaniwww.com
```

You can inspect them with:

```bash
docker inspect searxng-web-crawler-app
```

## License

MIT
