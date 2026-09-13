from __future__ import annotations

import csv
import hashlib
import io
import ipaddress
import json
import re
import socket
import threading
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import requests
import trafilatura
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import (
    ARCHIVES_DIR,
    CONNECT_TIMEOUT,
    CRAWL_WORKERS,
    MAX_HTML_SIZE,
    MAX_SEARCH_PAGES,
    READ_TIMEOUT,
    RESPECT_ROBOTS_TXT,
    SEARCH_TIMEOUT,
    SEARXNG_URL,
    SITES_DIR,
    USER_AGENT,
)
from .storage import upsert_document

TRACKING_PARAMS = {
    'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content', 'utm_id',
    'fbclid', 'gclid', 'dclid', 'msclkid', 'mc_cid', 'mc_eid',
}
thread_local = threading.local()


def get_session() -> requests.Session:
    if not hasattr(thread_local, 'session'):
        session = requests.Session()
        retry = Retry(
            total=2,
            connect=2,
            read=2,
            status=2,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods={'GET'},
            respect_retry_after_header=True,
        )
        adapter = HTTPAdapter(max_retries=retry, pool_connections=30, pool_maxsize=30)
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        session.headers.update({
            'User-Agent': USER_AGENT,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9,fa;q=0.8',
        })
        thread_local.session = session
    return thread_local.session


def safe_filename(text: str | None, max_length: int = 80) -> str:
    text = str(text or 'untitled').strip()
    text = re.sub(r'[\\/*?:"<>|]', '', text)
    text = re.sub(r'\s+', '_', text).strip('._ ')
    return (text or 'untitled')[:max_length]


def get_domain(url: str) -> str:
    try:
        domain = urlsplit(url).netloc.lower()
        return domain[4:] if domain.startswith('www.') else (domain or 'unknown')
    except Exception:
        return 'unknown'


def normalize_url(url: str) -> str:
    try:
        parts = urlsplit(url)
        if parts.scheme not in {'http', 'https'}:
            return url
        query = [
            (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
            if k.lower() not in TRACKING_PARAMS
        ]
        path = parts.path if parts.path == '/' else parts.path.rstrip('/')
        return urlunsplit((
            parts.scheme.lower(),
            parts.netloc.lower(),
            path,
            urlencode(query, doseq=True),
            '',
        ))
    except Exception:
        return url


def short_hash(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8', errors='ignore')).hexdigest()[:10]


def _is_public_ip(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    return not (
        addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_multicast
        or addr.is_reserved or addr.is_unspecified
    )


def validate_public_url(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme not in {'http', 'https'} or not parts.hostname:
        raise ValueError('Only public http/https URLs are allowed')
    try:
        infos = socket.getaddrinfo(
            parts.hostname,
            parts.port or (443 if parts.scheme == 'https' else 80),
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror as exc:
        raise ValueError(f'DNS lookup failed: {exc}') from exc
    ips = {info[4][0] for info in infos}
    if not ips or not all(_is_public_ip(ip) for ip in ips):
        raise ValueError('Blocked private/local/reserved target')


def robots_allowed(url: str) -> bool:
    if not RESPECT_ROBOTS_TXT:
        return True
    parts = urlsplit(url)
    robots_url = f'{parts.scheme}://{parts.netloc}/robots.txt'
    try:
        validate_public_url(robots_url)
        response = get_session().get(
            robots_url,
            timeout=(CONNECT_TIMEOUT, 10),
            allow_redirects=True,
        )
        if response.status_code >= 400:
            return True
        rp = RobotFileParser()
        rp.set_url(robots_url)
        rp.parse(response.text.splitlines())
        return rp.can_fetch(USER_AGENT, url)
    except Exception:
        return True


def search_searxng_page(keyword: str, page: int) -> dict:
    response = requests.get(
        f'{SEARXNG_URL}/search',
        params={'q': keyword, 'format': 'json', 'pageno': page},
        timeout=SEARCH_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


def collect_search_results(keyword: str, max_results: int = 100) -> list[dict]:
    """Best-effort collection of unique URLs from paginated SearXNG results."""
    unique: dict[str, dict] = {}
    no_growth_pages = 0

    print(f'[SEARCH] query={keyword!r} target={max_results:,} max_pages={MAX_SEARCH_PAGES:,}', flush=True)

    for page in range(1, MAX_SEARCH_PAGES + 1):
        if len(unique) >= max_results:
            break

        try:
            data = search_searxng_page(keyword, page)
        except Exception as exc:
            print(f'[SEARCH] page={page} failed: {type(exc).__name__}: {exc}', flush=True)
            no_growth_pages += 1
            if no_growth_pages >= 5:
                break
            continue

        page_results = data.get('results', [])
        before = len(unique)

        for item in page_results:
            original_url = item.get('url')
            if not original_url or not original_url.startswith(('http://', 'https://')):
                continue
            normalized = normalize_url(original_url)
            if normalized in unique:
                continue
            unique[normalized] = {
                'position': len(unique) + 1,
                'title': item.get('title'),
                'url': original_url,
                'normalized_url': normalized,
                'domain': get_domain(original_url),
                'content': item.get('content'),
                'engine': item.get('engine'),
                'engines': item.get('engines', []),
                'score': item.get('score'),
                'category': item.get('category'),
                'published_date': item.get('publishedDate'),
            }
            if len(unique) >= max_results:
                break

        added = len(unique) - before
        print(f'[SEARCH] page={page} +{added} unique={len(unique):,}/{max_results:,}', flush=True)
        no_growth_pages = no_growth_pages + 1 if added == 0 else 0
        if no_growth_pages >= 5:
            break

    print(f'[SEARCH] collected={len(unique):,}', flush=True)
    return list(unique.values())[:max_results]


def download_html(url: str) -> dict:
    validate_public_url(url)
    if not robots_allowed(url):
        return {'success': False, 'error': 'Blocked by robots.txt', 'final_url': url}

    session = get_session()
    current = url
    for _ in range(6):
        validate_public_url(current)
        response = session.get(
            current,
            timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
            allow_redirects=False,
            stream=True,
        )
        if response.is_redirect or response.is_permanent_redirect:
            location = response.headers.get('Location')
            if not location:
                break
            current = urljoin(current, location)
            continue

        response.raise_for_status()
        content_type = response.headers.get('Content-Type', '').lower()
        if 'text/html' not in content_type and 'application/xhtml+xml' not in content_type:
            return {
                'success': False,
                'error': f'Unsupported content type: {content_type}',
                'final_url': current,
            }

        content_length = response.headers.get('Content-Length')
        if content_length and content_length.isdigit() and int(content_length) > MAX_HTML_SIZE:
            return {'success': False, 'error': 'HTML file is too large', 'final_url': current}

        chunks: list[bytes] = []
        total = 0
        for chunk in response.iter_content(chunk_size=64 * 1024):
            if not chunk:
                continue
            total += len(chunk)
            if total > MAX_HTML_SIZE:
                return {'success': False, 'error': 'HTML exceeded maximum size', 'final_url': current}
            chunks.append(chunk)

        raw = b''.join(chunks)
        encoding = response.encoding or 'utf-8'
        try:
            html = raw.decode(encoding, errors='replace')
        except LookupError:
            html = raw.decode('utf-8', errors='replace')

        return {
            'success': True,
            'html': html,
            'final_url': current,
            'http_status': response.status_code,
            'content_type': content_type,
            'html_size': len(raw),
        }

    return {'success': False, 'error': 'Too many redirects', 'final_url': current}


def meta_content(soup: BeautifulSoup, *names: str) -> str | None:
    for name in names:
        tag = soup.find('meta', attrs={'name': name}) or soup.find('meta', attrs={'property': name})
        if tag and tag.get('content'):
            return str(tag['content']).strip()
    return None


def extract_metadata(html: str) -> dict:
    soup = BeautifulSoup(html, 'html.parser')
    title = meta_content(soup, 'og:title', 'twitter:title')
    if not title and soup.title:
        title = soup.title.get_text(' ', strip=True)
    canonical_tag = soup.find('link', attrs={'rel': 'canonical'})
    return {
        'title': title,
        'description': meta_content(soup, 'description', 'og:description', 'twitter:description'),
        'author': meta_content(soup, 'author', 'article:author'),
        'published_date': meta_content(soup, 'article:published_time', 'datePublished', 'date'),
        'site_name': meta_content(soup, 'og:site_name'),
        'canonical': canonical_tag.get('href') if canonical_tag else None,
    }


def extract_markdown(html: str, url: str, title: str | None = None) -> str | None:
    markdown = trafilatura.extract(
        html,
        url=url,
        output_format='markdown',
        include_comments=False,
        include_tables=True,
        include_links=True,
        include_images=True,
        favor_precision=True,
    )
    if markdown and len(markdown.strip()) >= 100:
        return markdown.strip()

    soup = BeautifulSoup(html, 'html.parser')
    for tag in soup(['script', 'style', 'noscript', 'nav', 'footer', 'header', 'aside', 'form', 'iframe', 'svg']):
        tag.decompose()
    lines: list[str] = []
    for line in soup.get_text('\n', strip=True).splitlines():
        line = line.strip()
        if line and (not lines or line != lines[-1]):
            lines.append(line)
    text = '\n\n'.join(lines)
    if not text:
        return None
    return f'# {title}\n\n{text}' if title else text


def make_markdown_document(metadata: dict, markdown: str, original_url: str, final_url: str) -> str:
    def y(value):
        return 'null' if value is None else json.dumps(str(value), ensure_ascii=False)

    now = datetime.now(timezone.utc).isoformat()
    return (
        f'---\n'
        f'title: {y(metadata.get("title"))}\n'
        f'site_name: {y(metadata.get("site_name"))}\n'
        f'url: {y(original_url)}\n'
        f'final_url: {y(final_url)}\n'
        f'domain: {y(get_domain(final_url))}\n'
        f'author: {y(metadata.get("author"))}\n'
        f'published_date: {y(metadata.get("published_date"))}\n'
        f'description: {y(metadata.get("description"))}\n'
        f'scraped_at: {y(now)}\n'
        f'---\n\n{markdown}'
    )


def crawl_result(result: dict, search_query: str) -> dict:
    original_url = result['url']
    try:
        download = download_html(original_url)
        if not download['success']:
            return {
                **result,
                'crawl_status': 'failed',
                'crawl_error': download['error'],
                'final_url': download.get('final_url'),
            }

        html = download['html']
        final_url = download['final_url']
        metadata = extract_metadata(html)
        markdown = extract_markdown(html, final_url, metadata.get('title'))
        if not markdown:
            return {
                **result,
                'crawl_status': 'failed',
                'crawl_error': 'Could not extract readable content',
                'final_url': final_url,
            }

        document = make_markdown_document(metadata, markdown, original_url, final_url)
        domain = get_domain(final_url)
        title = metadata.get('title') or result.get('title') or 'page'
        filename = f'{safe_filename(title, 60)}__{short_hash(final_url)}.md'
        relative_path = Path('sites') / safe_filename(domain, 80) / filename
        disk_path = SITES_DIR / safe_filename(domain, 80) / filename
        disk_path.parent.mkdir(parents=True, exist_ok=True)
        disk_path.write_text(document, encoding='utf-8')

        plain_hash = hashlib.sha256(markdown.encode('utf-8', errors='ignore')).hexdigest()
        doc = {
            'url': original_url,
            'normalized_url': normalize_url(original_url),
            'final_url': final_url,
            'domain': domain,
            'title': metadata.get('title') or result.get('title'),
            'description': metadata.get('description'),
            'author': metadata.get('author'),
            'published_date': metadata.get('published_date'),
            'site_name': metadata.get('site_name'),
            'search_query': search_query,
            'markdown_path': str(disk_path),
            'markdown': document,
            'content_hash': plain_hash,
            'characters': len(markdown),
            'http_status': download.get('http_status'),
        }
        doc_id = upsert_document(doc)

        return {
            **result,
            'document_id': doc_id,
            'crawl_status': 'completed',
            'crawl_error': None,
            'final_url': final_url,
            'final_domain': domain,
            'page_title': doc['title'],
            'description': doc['description'],
            'author': doc['author'],
            'page_published_date': doc['published_date'],
            'site_name': doc['site_name'],
            'canonical': metadata.get('canonical'),
            'http_status': download.get('http_status'),
            'html_size': download.get('html_size'),
            'markdown_characters': len(markdown),
            'markdown_file': str(relative_path).replace('\\', '/'),
            '_markdown_document': document,
            '_extracted_markdown': markdown,
        }
    except Exception as exc:
        status = getattr(getattr(exc, 'response', None), 'status_code', None)
        return {
            **result,
            'crawl_status': 'failed',
            'http_status': status,
            'crawl_error': f'{type(exc).__name__}: {exc}',
        }


def crawl_all_results(results: list[dict], search_query: str, progress_callback=None) -> list[dict]:
    crawled: list[dict] = []
    total = len(results)
    print(f'[CRAWL] starting {total:,} URLs with {CRAWL_WORKERS} workers', flush=True)

    with ThreadPoolExecutor(max_workers=CRAWL_WORKERS) as executor:
        futures = {executor.submit(crawl_result, result, search_query): result for result in results}
        for completed, future in enumerate(as_completed(futures), start=1):
            item = future.result()
            crawled.append(item)
            if progress_callback:
                progress_callback(completed, total, item)
            if completed == 1 or completed % 25 == 0 or completed == total:
                ok = sum(1 for x in crawled if x.get('crawl_status') == 'completed')
                print(f'[CRAWL] {completed:,}/{total:,} done · success={ok:,} · failed={completed-ok:,}', flush=True)

    crawled.sort(key=lambda x: x.get('position', 999999))
    return crawled


def _public_result(result: dict, include_markdown: bool = True) -> dict:
    row = {k: v for k, v in result.items() if not k.startswith('_')}
    if include_markdown and result.get('_extracted_markdown'):
        row['extracted_markdown'] = result['_extracted_markdown']
    return row


def _results_csv(results: list[dict]) -> str:
    fields = [
        'position', 'title', 'url', 'normalized_url', 'final_url', 'domain', 'final_domain',
        'engine', 'engines', 'score', 'category', 'published_date', 'page_published_date',
        'author', 'site_name', 'description', 'crawl_status', 'crawl_error', 'http_status',
        'markdown_characters', 'markdown_file', 'extracted_markdown',
    ]
    buf = io.StringIO(newline='')
    writer = csv.DictWriter(buf, fieldnames=fields, extrasaction='ignore')
    writer.writeheader()
    for result in results:
        row = _public_result(result, include_markdown=True)
        row['engines'] = ', '.join(row.get('engines') or [])
        writer.writerow(row)
    return buf.getvalue()


def _collection_markdown(keyword: str, results: list[dict]) -> str:
    parts = [f'# Web collection: {keyword}', '']
    for result in results:
        if result.get('crawl_status') != 'completed':
            continue
        title = result.get('page_title') or result.get('title') or 'Untitled'
        url = result.get('final_url') or result.get('url') or ''
        body = result.get('_extracted_markdown') or ''
        parts.extend([
            f'# {title}',
            '',
            f'Source: {url}',
            '',
            body,
            '',
            '---',
            '',
        ])
    return '\n'.join(parts).strip() + '\n'


def create_archive(keyword: str, results: list[dict]) -> Path:
    """Create ZIP plus directly downloadable JSON, CSV and MD sidecar exports."""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    stem = f'{safe_filename(keyword)}_{timestamp}'
    archive = ARCHIVES_DIR / f'{stem}.zip'
    json_path = ARCHIVES_DIR / f'{stem}.json'
    csv_path = ARCHIVES_DIR / f'{stem}.csv'
    md_path = ARCHIVES_DIR / f'{stem}.md'

    public_results = [_public_result(result, include_markdown=True) for result in results]
    failed = [r for r in public_results if r.get('crawl_status') != 'completed']
    payload = {
        'query': keyword,
        'created_at': datetime.now(timezone.utc).isoformat(),
        'total_results': len(public_results),
        'successful_crawls': sum(1 for r in public_results if r.get('crawl_status') == 'completed'),
        'failed_crawls': len(failed),
        'results': public_results,
    }

    json_text = json.dumps(payload, ensure_ascii=False, indent=2)
    csv_text = _results_csv(results)
    md_text = _collection_markdown(keyword, results)

    json_path.write_text(json_text, encoding='utf-8')
    csv_path.write_text(csv_text, encoding='utf-8-sig')
    md_path.write_text(md_text, encoding='utf-8')

    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for result in results:
            document = result.get('_markdown_document')
            if result.get('crawl_status') == 'completed' and document:
                zf.writestr(result['markdown_file'], document.encode('utf-8'))
        zf.writestr('results.json', json_text.encode('utf-8'))
        zf.writestr('results.csv', csv_text.encode('utf-8-sig'))
        zf.writestr('collection.md', md_text.encode('utf-8'))
        if failed:
            zf.writestr('failed.json', json.dumps(failed, ensure_ascii=False, indent=2).encode('utf-8'))

    print(f'[EXPORT] ZIP/JSON/CSV/MD created for {stem}', flush=True)
    return archive
