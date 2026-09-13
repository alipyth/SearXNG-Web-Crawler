from app.corpus import clean_markdown, content_hash
from app.crawler import normalize_url


def test_normalize_url_removes_tracking_and_fragment():
    url = 'https://example.com/a/?utm_source=x&keep=1#part'
    assert normalize_url(url) == 'https://example.com/a?keep=1'


def test_clean_markdown_removes_frontmatter_images_and_links():
    text = '''---
title: X
url: "https://example.com"
---

# Hello

![x](https://example.com/a.png)

Read [this article](https://example.com/article) now.
Raw: https://example.com/another

World
'''
    cleaned = clean_markdown(text)
    assert 'title: X' not in cleaned
    assert 'a.png' not in cleaned
    assert 'https://' not in cleaned
    assert '[this article]' not in cleaned
    assert 'this article' in cleaned
    assert '# Hello' in cleaned


def test_hash_is_whitespace_stable():
    assert content_hash('Hello   world') == content_hash('Hello\nworld')
