from __future__ import annotations

import argparse
from pathlib import Path

from .config import MAX_RESULTS_DEFAULT, MAX_RESULTS_LIMIT
from .corpus import build_corpus_from_zip
from .crawler import collect_search_results, crawl_all_results, create_archive
from .storage import init_db


def main() -> None:
    parser = argparse.ArgumentParser(
        prog='searxng-crawler',
        description='Search with SearXNG, crawl public pages, export JSON/CSV/Markdown, and build clean LLM corpora.',
    )
    sub = parser.add_subparsers(dest='command', required=True)

    search = sub.add_parser('search', help='Search and crawl the web')
    search.add_argument('query')
    search.add_argument('--max-results', type=int, default=MAX_RESULTS_DEFAULT)

    corpus = sub.add_parser('corpus', help='Build clean MD/JSON/CSV corpora from a generated ZIP')
    corpus.add_argument('zip_file', type=Path)

    args = parser.parse_args()
    init_db()

    if args.command == 'search':
        if not 1 <= args.max_results <= MAX_RESULTS_LIMIT:
            parser.error(f'--max-results must be between 1 and {MAX_RESULTS_LIMIT}')
        results = collect_search_results(args.query, args.max_results)
        crawled = crawl_all_results(results, args.query)
        archive = create_archive(args.query, crawled)
        print(f'Archive: {archive}')
        print(f'JSON:    {archive.with_suffix(".json")}')
        print(f'CSV:     {archive.with_suffix(".csv")}')
        print(f'MD:      {archive.with_suffix(".md")}')
    elif args.command == 'corpus':
        print(build_corpus_from_zip(args.zip_file))


if __name__ == '__main__':
    main()
