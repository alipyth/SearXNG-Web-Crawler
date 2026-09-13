from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv('DATA_DIR', BASE_DIR / 'data')).resolve()
SITES_DIR = DATA_DIR / 'sites'
ARCHIVES_DIR = DATA_DIR / 'archives'
CORPORA_DIR = DATA_DIR / 'corpora'
DB_PATH = DATA_DIR / 'library.db'

SEARXNG_URL = os.getenv('SEARXNG_URL', 'http://searxng:8080').rstrip('/')
MAX_RESULTS_DEFAULT = int(os.getenv('MAX_RESULTS', '100'))
MAX_RESULTS_LIMIT = int(os.getenv('MAX_RESULTS_LIMIT', '10000'))
MAX_SEARCH_PAGES = int(os.getenv('MAX_SEARCH_PAGES', '2000'))
CRAWL_WORKERS = int(os.getenv('CRAWL_WORKERS', '6'))
SEARCH_TIMEOUT = int(os.getenv('SEARCH_TIMEOUT', '30'))
CONNECT_TIMEOUT = int(os.getenv('CONNECT_TIMEOUT', '10'))
READ_TIMEOUT = int(os.getenv('READ_TIMEOUT', '30'))
MAX_HTML_SIZE = int(os.getenv('MAX_HTML_SIZE', str(8 * 1024 * 1024)))
MIN_CONTENT_LENGTH = int(os.getenv('MIN_CONTENT_LENGTH', '300'))
RESPECT_ROBOTS_TXT = os.getenv('RESPECT_ROBOTS_TXT', 'true').lower() in {'1', 'true', 'yes', 'on'}
USER_AGENT = os.getenv(
    'USER_AGENT',
    'Mozilla/5.0 (compatible; SearXNG-Web-Crawler/2.0; +https://github.com/alipyth/SearXNG-Web-Crawler)'
)

APP_DEVELOPER = os.getenv('APP_DEVELOPER', 'Ali Jahani')
APP_TELEGRAM = os.getenv('APP_TELEGRAM', 'https://t.me/tarfandoonchannel')
APP_WEBSITE = os.getenv('APP_WEBSITE', 'https://jahaniwww.com')

for path in (DATA_DIR, SITES_DIR, ARCHIVES_DIR, CORPORA_DIR):
    path.mkdir(parents=True, exist_ok=True)
