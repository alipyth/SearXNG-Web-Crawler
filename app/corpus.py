from __future__ import annotations

import hashlib
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


def clean_markdown(text: str, remove_images: bool = True, remove_html: bool = True) -> str:
    text = strip_frontmatter(text)
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    if remove_images:
        text = re.sub(r'!\[[^\]]*\]\([^)]+\)', '', text)
    if remove_html:
        text = re.sub(r'<[^>]+>', '', text)
    text = text.replace('\u200b', '').replace('\ufeff', '')
    text = '\n'.join(line.rstrip() for line in text.splitlines())
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'[ \t]{2,}', ' ', text)
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


def build_corpus_from_directory(directory: Path, output_path: Path, include_source_info: bool = False) -> dict:
    files = sorted(directory.rglob('*.md'), key=lambda p: str(p).lower())
    seen: set[str] = set()
    documents: list[str] = []
    duplicate_count = too_short_count = error_count = total_characters = 0

    for path in files:
        try:
            raw = path.read_text(encoding='utf-8', errors='ignore')
        except Exception:
            error_count += 1
            continue
        text = clean_markdown(raw)
        if len(text) < MIN_CONTENT_LENGTH:
            too_short_count += 1
            continue
        h = content_hash(text)
        if h in seen:
            duplicate_count += 1
            continue
        seen.add(h)
        if include_source_info:
            text = f'<!-- SOURCE: {path.relative_to(directory)} -->\n\n{text}'
        documents.append(text)
        total_characters += len(text)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text('\n\n---\n\n'.join(documents), encoding='utf-8')
    return {
        'files_found': len(files),
        'documents_saved': len(documents),
        'duplicates': duplicate_count,
        'too_short': too_short_count,
        'errors': error_count,
        'characters': total_characters,
        'output': str(output_path),
    }


def build_corpus_from_zip(zip_path: Path, include_source_info: bool = False) -> dict:
    work_dir = zip_path.parent / f'.{zip_path.stem}_corpus_tmp'
    safe_extract_zip(zip_path, work_dir)
    output_path = CORPORA_DIR / f'{zip_path.stem}_training_corpus.md'
    try:
        return build_corpus_from_directory(work_dir, output_path, include_source_info)
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
