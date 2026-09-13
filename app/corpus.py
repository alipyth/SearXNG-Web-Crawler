from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import shutil
import zipfile
from pathlib import Path

from .config import CORPORA_DIR, MIN_CONTENT_LENGTH


def strip_frontmatter(text: str) -> str:
    text = text.lstrip('\ufeff')
    if not text.startswith('---'):
        return text
    match = re.match(r'^---\s*\n.*?\n---\s*\n', text, flags=re.DOTALL)
    return text[match.end():] if match else text


def remove_links_keep_text(text: str) -> str:
    """Remove link destinations while keeping human-readable anchor text."""
    # Images first: remove the entire image token.
    text = re.sub(r'!\[[^\]]*\]\([^)]*\)', '', text)
    text = re.sub(r'!\[[^\]]*\]\[[^\]]*\]', '', text)

    # Inline links: [Readable text](https://...) -> Readable text
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    # Reference-style links: [Readable text][ref] -> Readable text
    text = re.sub(r'\[([^\]]+)\]\[[^\]]*\]', r'\1', text)
    # Reference definitions: [ref]: https://...
    text = re.sub(r'^\s*\[[^\]]+\]:\s*(?:https?://|//)\S+.*$', '', text, flags=re.MULTILINE | re.IGNORECASE)
    # Autolinks: <https://...>
    text = re.sub(r'<(?:https?://|mailto:)[^>]+>', '', text, flags=re.IGNORECASE)
    # Raw URLs.
    text = re.sub(r'(?<!\w)(?:https?://|www\.)\S+', '', text, flags=re.IGNORECASE)
    return text


def clean_markdown(
    text: str,
    remove_images: bool = True,
    remove_html: bool = True,
    remove_links: bool = True,
) -> str:
    """Turn scraped Markdown into clean book-like training text."""
    text = strip_frontmatter(text)
    text = text.replace('\r\n', '\n').replace('\r', '\n')

    if remove_links:
        text = remove_links_keep_text(text)
    elif remove_images:
        text = re.sub(r'!\[[^\]]*\]\([^)]+\)', '', text)

    if remove_html:
        text = re.sub(r'<[^>]+>', '', text)

    text = text.replace('\u200b', '').replace('\ufeff', '').replace('\u00a0', ' ')

    # Remove common source/link-only lines that add little training value.
    text = re.sub(r'^\s*(?:source|url|link)\s*:\s*.*$', '', text, flags=re.MULTILINE | re.IGNORECASE)

    lines = []
    previous = None
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        # Clean trailing spaces and obvious empty Markdown link remnants.
        line = re.sub(r'[ \t]{2,}', ' ', line)
        if line.strip() and line.strip() == previous:
            continue
        lines.append(line)
        if line.strip():
            previous = line.strip()

    text = '\n'.join(lines)
    text = re.sub(r'\n{3,}', '\n\n', text)
    # Avoid huge runs of horizontal separators from merged source documents.
    text = re.sub(r'(?:\n?\s*---\s*\n?){2,}', '\n\n', text)
    return text.strip()


def normalize_for_hash(text: str) -> str:
    text = text.lower()
    text = re.sub(r'[#>*_`~\-]+', ' ', text)
    return re.sub(r'\s+', ' ', text).strip()


def content_hash(text: str) -> str:
    return hashlib.sha256(normalize_for_hash(text).encode('utf-8', errors='ignore')).hexdigest()


def safe_extract_zip(zip_path: Path, extract_dir: Path) -> None:
    if extract_dir.exists():
        shutil.rmtree(extract_dir)
    extract_dir.mkdir(parents=True, exist_ok=True)
    root = extract_dir.resolve()
    with zipfile.ZipFile(zip_path, 'r') as zf:
        for member in zf.infolist():
            target = (extract_dir / member.filename).resolve()
            if root not in target.parents and target != root:
                raise ValueError(f'Unsafe ZIP path: {member.filename}')
        zf.extractall(extract_dir)


def _collect_clean_documents(directory: Path, include_source_info: bool = False) -> tuple[list[dict], dict]:
    files = sorted(directory.rglob('*.md'), key=lambda p: str(p).lower())
    # Ignore aggregate Markdown already present in the archive; only per-page files belong under sites/.
    site_files = [p for p in files if 'sites' in p.parts]
    if site_files:
        files = site_files

    seen: set[str] = set()
    documents: list[dict] = []
    duplicate_count = too_short_count = error_count = total_characters = 0

    for path in files:
        try:
            raw = path.read_text(encoding='utf-8', errors='ignore')
        except Exception:
            error_count += 1
            continue

        text = clean_markdown(raw, remove_images=True, remove_html=True, remove_links=True)
        if len(text) < MIN_CONTENT_LENGTH:
            too_short_count += 1
            continue

        h = content_hash(text)
        if h in seen:
            duplicate_count += 1
            continue
        seen.add(h)

        if include_source_info:
            # Disabled by default; useful only for debugging/provenance.
            text = f'<!-- SOURCE: {path.relative_to(directory)} -->\n\n{text}'

        documents.append({
            'index': len(documents) + 1,
            'content': text,
            'characters': len(text),
        })
        total_characters += len(text)

    stats = {
        'files_found': len(files),
        'documents_saved': len(documents),
        'duplicates': duplicate_count,
        'too_short': too_short_count,
        'errors': error_count,
        'characters': total_characters,
    }
    return documents, stats


def _write_corpus_formats(documents: list[dict], base_path: Path) -> dict[str, str]:
    base_path.parent.mkdir(parents=True, exist_ok=True)
    md_path = base_path.with_suffix('.md')
    json_path = base_path.with_suffix('.json')
    csv_path = base_path.with_suffix('.csv')

    # Book-like Markdown: no URLs, source headers, frontmatter, or external-link syntax.
    md_text = '\n\n\n'.join(doc['content'] for doc in documents).strip() + ('\n' if documents else '')
    md_path.write_text(md_text, encoding='utf-8')

    json_payload = {
        'format': 'clean-book-corpus',
        'documents': documents,
        'total_documents': len(documents),
        'total_characters': sum(doc['characters'] for doc in documents),
    }
    json_path.write_text(json.dumps(json_payload, ensure_ascii=False, indent=2), encoding='utf-8')

    buf = io.StringIO(newline='')
    writer = csv.DictWriter(buf, fieldnames=['index', 'characters', 'content'])
    writer.writeheader()
    writer.writerows(documents)
    csv_path.write_text(buf.getvalue(), encoding='utf-8-sig')

    return {'md': str(md_path), 'json': str(json_path), 'csv': str(csv_path)}


def build_corpus_from_directory(
    directory: Path,
    output_base: Path,
    include_source_info: bool = False,
) -> dict:
    documents, stats = _collect_clean_documents(directory, include_source_info=include_source_info)
    outputs = _write_corpus_formats(documents, output_base)
    return {**stats, 'outputs': outputs}


def build_corpus_from_zip(zip_path: Path, include_source_info: bool = False) -> dict:
    work_dir = zip_path.parent / f'.{zip_path.stem}_corpus_tmp'
    safe_extract_zip(zip_path, work_dir)
    output_base = CORPORA_DIR / f'{zip_path.stem}_clean_corpus'
    try:
        return build_corpus_from_directory(work_dir, output_base, include_source_info)
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
