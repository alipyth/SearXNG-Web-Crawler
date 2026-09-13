from app.corpus import clean_markdown, content_hash
from app.crawler import normalize_url


def test_normalize_url_removes_tracking_and_fragment():
    url = 'https://example.com/a/?utm_source=x&keep=1#part'
    assert normalize_url(url) == 'https://example.com/a?keep=1'


def test_clean_markdown_removes_frontmatter_and_images():
    text = '---\ntitle: X\n---\n\n# Hello\n\n![x](a.png)\n\nWorld'
    cleaned = clean_markdown(text)
    assert 'title: X' not in cleaned
    assert 'a.png' not in cleaned
    assert '# Hello' in cleaned


def test_hash_is_whitespace_stable():
    assert content_hash('Hello   world') == content_hash('Hello\nworld')
