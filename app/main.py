from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from starlette.requests import Request

from .config import (
    APP_DEVELOPER,
    APP_TELEGRAM,
    APP_WEBSITE,
    ARCHIVES_DIR,
    CORPORA_DIR,
    MAX_RESULTS_DEFAULT,
    MAX_RESULTS_LIMIT,
    SEARXNG_URL,
)
from .corpus import build_corpus_from_zip
from .crawler import collect_search_results, crawl_all_results, create_archive
from .storage import (
    create_job,
    delete_document,
    delete_job,
    get_document,
    get_job,
    init_db,
    list_jobs,
    search_documents,
    stats,
    update_job,
)

APP_NAME = 'SearXNG Web Crawler'
app = FastAPI(title=APP_NAME, version='2.0.0')
app.mount('/static', StaticFiles(directory=Path(__file__).parent / 'static'), name='static')
templates = Jinja2Templates(directory=Path(__file__).parent / 'templates')


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=300)
    max_results: int = Field(default=MAX_RESULTS_DEFAULT, ge=1, le=MAX_RESULTS_LIMIT)


def _banner() -> str:
    return f'''
╔══════════════════════════════════════════════════════════════════╗
║                     SearXNG WEB CRAWLER                         ║
║          Search • Crawl • Clean • Export • Build Corpus         ║
╠══════════════════════════════════════════════════════════════════╣
║ Developed by : {APP_DEVELOPER:<49}║
║ Telegram     : {APP_TELEGRAM:<49}║
║ Website      : {APP_WEBSITE:<49}║
╚══════════════════════════════════════════════════════════════════╝
'''


@app.on_event('startup')
def startup() -> None:
    init_db()
    print(_banner(), flush=True)
    print(f'[APP] SearXNG endpoint: {SEARXNG_URL}', flush=True)
    print(f'[APP] Maximum requested results per job: {MAX_RESULTS_LIMIT:,}', flush=True)


@app.get('/', response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(
        'index.html',
        {
            'request': request,
            'searxng_url': SEARXNG_URL,
            'max_results_limit': MAX_RESULTS_LIMIT,
            'developer': APP_DEVELOPER,
            'telegram': APP_TELEGRAM,
            'website': APP_WEBSITE,
        },
    )


def _run_search_job(job_id: str, query: str, max_results: int) -> None:
    try:
        update_job(job_id, status='searching')
        results = collect_search_results(query, max_results)
        update_job(job_id, status='crawling', found=len(results))

        failed_count = 0

        def progress(done: int, total: int, item: dict):
            nonlocal failed_count
            if item.get('crawl_status') != 'completed':
                failed_count += 1
            update_job(job_id, crawled=done, failed=failed_count)

        crawled = crawl_all_results(results, query, progress)
        archive = create_archive(query, crawled)
        failed = sum(1 for r in crawled if r.get('crawl_status') != 'completed')
        update_job(
            job_id,
            status='completed',
            crawled=len(crawled),
            failed=failed,
            archive_path=str(archive),
            finished_at=datetime.now(timezone.utc).isoformat(),
        )
    except Exception as exc:
        print(f'[JOB] {job_id} failed: {type(exc).__name__}: {exc}', flush=True)
        update_job(
            job_id,
            status='failed',
            error=f'{type(exc).__name__}: {exc}',
            finished_at=datetime.now(timezone.utc).isoformat(),
        )


@app.post('/api/search')
def start_search(body: SearchRequest):
    job_id = uuid.uuid4().hex
    query = body.query.strip()
    create_job(job_id, query, body.max_results)
    threading.Thread(
        target=_run_search_job,
        args=(job_id, query, body.max_results),
        daemon=True,
    ).start()
    return {'job_id': job_id, 'requested_results': body.max_results}


@app.get('/api/jobs')
def api_jobs():
    return list_jobs()


@app.get('/api/jobs/{job_id}')
def api_job(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(404, 'Job not found')
    return job


@app.delete('/api/jobs/{job_id}')
def api_delete_job(job_id: str):
    job = delete_job(job_id)
    if not job:
        raise HTTPException(404, 'Job not found')
    return {'deleted': True, 'job_id': job_id}


@app.get('/api/library')
def api_library(
    q: str = Query(default='', max_length=300),
    limit: int = Query(default=50, ge=1, le=500),
):
    return search_documents(q, limit=limit)


@app.get('/api/library/{doc_id}')
def api_document(doc_id: int):
    doc = get_document(doc_id)
    if not doc:
        raise HTTPException(404, 'Document not found')
    return doc


@app.delete('/api/library/{doc_id}')
def api_delete_document(doc_id: int):
    doc = delete_document(doc_id)
    if not doc:
        raise HTTPException(404, 'Document not found')
    path_value = doc.get('markdown_path')
    if path_value:
        try:
            path = Path(path_value)
            if path.exists() and path.is_file():
                path.unlink()
        except OSError:
            pass
    return {'deleted': True, 'document_id': doc_id}


@app.get('/api/stats')
def api_stats():
    return stats()


def _safe_stem(stem: str) -> str:
    clean = Path(stem).name
    if clean != stem or clean in {'', '.', '..'}:
        raise HTTPException(400, 'Invalid file name')
    return clean


def _group_files(directory: Path, extensions: tuple[str, ...]) -> list[dict]:
    grouped: dict[str, dict] = {}
    for ext in extensions:
        for path in directory.glob(f'*.{ext}'):
            row = grouped.setdefault(path.stem, {'stem': path.stem, 'files': {}, 'total_size': 0})
            row['files'][ext] = {'name': path.name, 'size': path.stat().st_size}
            row['total_size'] += path.stat().st_size
            row['mtime'] = max(row.get('mtime', 0), path.stat().st_mtime)
    return sorted(grouped.values(), key=lambda x: x.get('mtime', 0), reverse=True)


@app.get('/api/archives')
def api_archives():
    return _group_files(ARCHIVES_DIR, ('zip', 'json', 'csv', 'md'))


@app.get('/api/archives/{stem}/{fmt}/download')
def download_archive_export(stem: str, fmt: str):
    stem = _safe_stem(stem)
    if fmt not in {'zip', 'json', 'csv', 'md'}:
        raise HTTPException(400, 'Unsupported format')
    path = (ARCHIVES_DIR / f'{stem}.{fmt}').resolve()
    if path.parent != ARCHIVES_DIR.resolve() or not path.exists():
        raise HTTPException(404, 'Export not found')
    media = {
        'zip': 'application/zip',
        'json': 'application/json',
        'csv': 'text/csv; charset=utf-8',
        'md': 'text/markdown; charset=utf-8',
    }[fmt]
    return FileResponse(path, filename=path.name, media_type=media)


@app.post('/api/archives/{stem}/build-corpus')
def build_corpus(stem: str):
    stem = _safe_stem(stem)
    path = (ARCHIVES_DIR / f'{stem}.zip').resolve()
    if path.parent != ARCHIVES_DIR.resolve() or not path.exists():
        raise HTTPException(404, 'Archive not found')
    return build_corpus_from_zip(path)


@app.delete('/api/archives/{stem}')
def delete_archive(stem: str):
    stem = _safe_stem(stem)
    deleted = []
    for fmt in ('zip', 'json', 'csv', 'md'):
        path = ARCHIVES_DIR / f'{stem}.{fmt}'
        if path.exists() and path.is_file():
            path.unlink()
            deleted.append(path.name)
    if not deleted:
        raise HTTPException(404, 'Archive not found')
    return {'deleted': deleted}


@app.get('/api/corpora')
def api_corpora():
    return _group_files(CORPORA_DIR, ('md', 'json', 'csv'))


@app.get('/api/corpora/{stem}/{fmt}/download')
def download_corpus(stem: str, fmt: str):
    stem = _safe_stem(stem)
    if fmt not in {'md', 'json', 'csv'}:
        raise HTTPException(400, 'Unsupported format')
    path = (CORPORA_DIR / f'{stem}.{fmt}').resolve()
    if path.parent != CORPORA_DIR.resolve() or not path.exists():
        raise HTTPException(404, 'Corpus not found')
    media = {
        'json': 'application/json',
        'csv': 'text/csv; charset=utf-8',
        'md': 'text/markdown; charset=utf-8',
    }[fmt]
    return FileResponse(path, filename=path.name, media_type=media)


@app.delete('/api/corpora/{stem}')
def delete_corpus(stem: str):
    stem = _safe_stem(stem)
    deleted = []
    for fmt in ('md', 'json', 'csv'):
        path = CORPORA_DIR / f'{stem}.{fmt}'
        if path.exists() and path.is_file():
            path.unlink()
            deleted.append(path.name)
    if not deleted:
        raise HTTPException(404, 'Corpus not found')
    return {'deleted': deleted}


@app.get('/api/health')
def health():
    return {
        'status': 'ok',
        'app': APP_NAME,
        'version': '2.0.0',
        'searxng_url': SEARXNG_URL,
        'max_results_limit': MAX_RESULTS_LIMIT,
        'developed_by': APP_DEVELOPER,
    }
