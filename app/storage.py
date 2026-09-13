from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import DB_PATH

_lock = threading.Lock()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL;')
    conn.execute('PRAGMA foreign_keys=ON;')
    return conn


def init_db() -> None:
    with _lock, _connect() as conn:
        conn.executescript(
            '''
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL,
                normalized_url TEXT NOT NULL UNIQUE,
                final_url TEXT,
                domain TEXT,
                title TEXT,
                description TEXT,
                author TEXT,
                published_date TEXT,
                site_name TEXT,
                search_query TEXT,
                markdown_path TEXT NOT NULL,
                markdown TEXT NOT NULL,
                content_hash TEXT,
                characters INTEGER DEFAULT 0,
                http_status INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_documents_domain ON documents(domain);
            CREATE INDEX IF NOT EXISTS idx_documents_created_at ON documents(created_at);
            CREATE INDEX IF NOT EXISTS idx_documents_content_hash ON documents(content_hash);

            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                query TEXT NOT NULL,
                requested_results INTEGER NOT NULL,
                status TEXT NOT NULL,
                found INTEGER DEFAULT 0,
                crawled INTEGER DEFAULT 0,
                failed INTEGER DEFAULT 0,
                archive_path TEXT,
                error TEXT,
                created_at TEXT NOT NULL,
                finished_at TEXT
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
                title,
                domain,
                markdown,
                content='documents',
                content_rowid='id'
            );

            CREATE TRIGGER IF NOT EXISTS documents_ai AFTER INSERT ON documents BEGIN
                INSERT INTO documents_fts(rowid, title, domain, markdown)
                VALUES (new.id, new.title, new.domain, new.markdown);
            END;

            CREATE TRIGGER IF NOT EXISTS documents_ad AFTER DELETE ON documents BEGIN
                INSERT INTO documents_fts(documents_fts, rowid, title, domain, markdown)
                VALUES ('delete', old.id, old.title, old.domain, old.markdown);
            END;

            CREATE TRIGGER IF NOT EXISTS documents_au AFTER UPDATE ON documents BEGIN
                INSERT INTO documents_fts(documents_fts, rowid, title, domain, markdown)
                VALUES ('delete', old.id, old.title, old.domain, old.markdown);
                INSERT INTO documents_fts(rowid, title, domain, markdown)
                VALUES (new.id, new.title, new.domain, new.markdown);
            END;
            '''
        )


def create_job(job_id: str, query: str, requested_results: int) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _lock, _connect() as conn:
        conn.execute(
            '''INSERT INTO jobs(id, query, requested_results, status, created_at)
               VALUES (?, ?, ?, 'queued', ?)''',
            (job_id, query, requested_results, now),
        )


def update_job(job_id: str, **fields: Any) -> None:
    if not fields:
        return
    allowed = {'status', 'found', 'crawled', 'failed', 'archive_path', 'error', 'finished_at'}
    clean = {k: v for k, v in fields.items() if k in allowed}
    if not clean:
        return
    assignments = ', '.join(f'{k} = ?' for k in clean)
    values = list(clean.values()) + [job_id]
    with _lock, _connect() as conn:
        conn.execute(f'UPDATE jobs SET {assignments} WHERE id = ?', values)


def get_job(job_id: str) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute('SELECT * FROM jobs WHERE id = ?', (job_id,)).fetchone()
    return dict(row) if row else None


def list_jobs(limit: int = 100) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            'SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?', (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def delete_job(job_id: str) -> dict[str, Any] | None:
    with _lock, _connect() as conn:
        row = conn.execute('SELECT * FROM jobs WHERE id = ?', (job_id,)).fetchone()
        if not row:
            return None
        conn.execute('DELETE FROM jobs WHERE id = ?', (job_id,))
    return dict(row)


def upsert_document(doc: dict[str, Any]) -> int:
    now = datetime.now(timezone.utc).isoformat()
    values = (
        doc.get('url'), doc.get('normalized_url'), doc.get('final_url'), doc.get('domain'),
        doc.get('title'), doc.get('description'), doc.get('author'), doc.get('published_date'),
        doc.get('site_name'), doc.get('search_query'), doc.get('markdown_path'),
        doc.get('markdown', ''), doc.get('content_hash'), doc.get('characters', 0),
        doc.get('http_status'), now, now,
    )
    with _lock, _connect() as conn:
        conn.execute(
            '''
            INSERT INTO documents(
                url, normalized_url, final_url, domain, title, description, author,
                published_date, site_name, search_query, markdown_path, markdown,
                content_hash, characters, http_status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(normalized_url) DO UPDATE SET
                final_url=excluded.final_url,
                domain=excluded.domain,
                title=excluded.title,
                description=excluded.description,
                author=excluded.author,
                published_date=excluded.published_date,
                site_name=excluded.site_name,
                search_query=excluded.search_query,
                markdown_path=excluded.markdown_path,
                markdown=excluded.markdown,
                content_hash=excluded.content_hash,
                characters=excluded.characters,
                http_status=excluded.http_status,
                updated_at=excluded.updated_at
            ''',
            values,
        )
        row = conn.execute(
            'SELECT id FROM documents WHERE normalized_url = ?', (doc.get('normalized_url'),)
        ).fetchone()
        return int(row['id'])


def search_documents(query: str = '', limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
    with _connect() as conn:
        if query.strip():
            try:
                rows = conn.execute(
                    '''
                    SELECT d.id, d.title, d.url, d.final_url, d.domain, d.description,
                           d.author, d.published_date, d.characters, d.markdown_path,
                           d.created_at,
                           snippet(documents_fts, 2, '<mark>', '</mark>', ' … ', 18) AS snippet
                    FROM documents_fts
                    JOIN documents d ON d.id = documents_fts.rowid
                    WHERE documents_fts MATCH ?
                    ORDER BY bm25(documents_fts)
                    LIMIT ? OFFSET ?
                    ''',
                    (query, limit, offset),
                ).fetchall()
            except sqlite3.OperationalError:
                like = f'%{query}%'
                rows = conn.execute(
                    '''SELECT id, title, url, final_url, domain, description, author,
                              published_date, characters, markdown_path, created_at,
                              substr(markdown, 1, 400) AS snippet
                       FROM documents
                       WHERE title LIKE ? OR domain LIKE ? OR markdown LIKE ?
                       ORDER BY created_at DESC LIMIT ? OFFSET ?''',
                    (like, like, like, limit, offset),
                ).fetchall()
        else:
            rows = conn.execute(
                '''SELECT id, title, url, final_url, domain, description, author,
                          published_date, characters, markdown_path, created_at,
                          substr(markdown, 1, 400) AS snippet
                   FROM documents ORDER BY created_at DESC LIMIT ? OFFSET ?''',
                (limit, offset),
            ).fetchall()
    return [dict(r) for r in rows]


def get_document(doc_id: int) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute('SELECT * FROM documents WHERE id = ?', (doc_id,)).fetchone()
    return dict(row) if row else None


def delete_document(doc_id: int) -> dict[str, Any] | None:
    with _lock, _connect() as conn:
        row = conn.execute('SELECT * FROM documents WHERE id = ?', (doc_id,)).fetchone()
        if not row:
            return None
        conn.execute('DELETE FROM documents WHERE id = ?', (doc_id,))
    return dict(row)


def stats() -> dict[str, Any]:
    with _connect() as conn:
        total = conn.execute('SELECT COUNT(*) c FROM documents').fetchone()['c']
        chars = conn.execute('SELECT COALESCE(SUM(characters),0) c FROM documents').fetchone()['c']
        domains = conn.execute('SELECT COUNT(DISTINCT domain) c FROM documents').fetchone()['c']
        jobs = conn.execute('SELECT COUNT(*) c FROM jobs').fetchone()['c']
    return {'documents': total, 'characters': chars, 'domains': domains, 'jobs': jobs}
