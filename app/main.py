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

from .config import ARCHIVES_DIR, CORPORA_DIR, MAX_RESULTS_DEFAULT, SEARXNG_URL
from .corpus import build_corpus_from_zip
from .crawler import collect_search_results, crawl_all_results, create_archive
from .storage import (
    create_job,
    get_document,
    get_job,
    init_db,
    list_jobs,
    search_documents,
    stats,
    update_job,
)

app = FastAPI(title='SearX Corpus Studio', version='1.0.0')
app.mount('/static', StaticFiles(directory=Path(__file__).parent / 'static'), name='static')
templates = Jinja2Templates(directory=Path(__file__).parent / 'templates')


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=300)
    max_results: int = Field(default=MAX_RESULTS_DEFAULT, ge=1, le=500)


@app.on_event('startup')
def startup() -> None:
    init_db()


@app.get('/', response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse('index.html', {'request': request, 'searxng_url': SEARXNG_URL})


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
        update_job(
            job_id,
            status='failed',
            error=f'{type(exc).__name__}: {exc}',
            finished_at=datetime.now(timezone.utc).isoformat(),
        )


@app.post('/api/search')
def start_search(body: SearchRequest):
    job_id = uuid.uuid4().hex
    create_job(job_id, body.query.strip(), body.max_results)
    threading.Thread(
        target=_run_search_job,
        args=(job_id, body.query.strip(), body.max_results),
        daemon=True,
    ).start()
    return {'job_id': job_id}


@app.get('/api/jobs')
def api_jobs():
    return list_jobs()


@app.get('/api/jobs/{job_id}')
def api_job(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(404, 'Job not found')
    return job


@app.get('/api/library')
def api_library(q: str = Query(default='', max_length=300), limit: int = Query(default=50, ge=1, le=200)):
    return search_documents(q, limit=limit)


@app.get('/api/library/{doc_id}')
def api_document(doc_id: int):
    doc = get_document(doc_id)
    if not doc:
        raise HTTPException(404, 'Document not found')
    return doc


@app.get('/api/stats')
def api_stats():
    return stats()


@app.get('/api/archives')
def api_archives():
    rows = []
    for path in sorted(ARCHIVES_DIR.glob('*.zip'), key=lambda p: p.stat().st_mtime, reverse=True):
        rows.append({'name': path.name, 'size': path.stat().st_size})
    return rows


@app.get('/api/archives/{name}/download')
def download_archive(name: str):
    path = (ARCHIVES_DIR / Path(name).name).resolve()
    if path.parent != ARCHIVES_DIR.resolve() or not path.exists():
        raise HTTPException(404, 'Archive not found')
    return FileResponse(path, filename=path.name, media_type='application/zip')


@app.post('/api/archives/{name}/build-corpus')
def build_corpus(name: str):
    path = (ARCHIVES_DIR / Path(name).name).resolve()
    if path.parent != ARCHIVES_DIR.resolve() or not path.exists():
        raise HTTPException(404, 'Archive not found')
    return build_corpus_from_zip(path)


@app.get('/api/corpora')
def api_corpora():
    return [
        {'name': p.name, 'size': p.stat().st_size}
        for p in sorted(CORPORA_DIR.glob('*.md'), key=lambda p: p.stat().st_mtime, reverse=True)
    ]


@app.get('/api/corpora/{name}/download')
def download_corpus(name: str):
    path = (CORPORA_DIR / Path(name).name).resolve()
    if path.parent != CORPORA_DIR.resolve() or not path.exists():
        raise HTTPException(404, 'Corpus not found')
    return FileResponse(path, filename=path.name, media_type='text/markdown; charset=utf-8')


@app.get('/api/health')
def health():
    return {'status': 'ok', 'searxng_url': SEARXNG_URL}
