import html
import ipaddress
import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path


SEARCH_URL = 'https://www.bing.com/search'
NEWS_FEEDS = (
    ('BBC News', 'https://feeds.bbci.co.uk/news/rss.xml'),
    ('NPR', 'https://feeds.npr.org/1001/rss.xml'),
    ('Ars Technica', 'https://feeds.arstechnica.com/arstechnica/index'),
)
USER_AGENT = 'Val/1.0 personal RSS reader'
MAX_RESPONSE_BYTES = 768 * 1024
store_lock = threading.Lock()


def clean_text(value, limit=420):
    value = html.unescape(re.sub(r'<[^>]+>', ' ', value or ''))
    value = re.sub(r'\s+', ' ', value).strip()
    return value[:limit].rstrip()


def public_result_url(value):
    try:
        parsed = urllib.parse.urlparse(value)
        if parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username or parsed.password:
            return None
        host = parsed.hostname.lower().rstrip('.')
        if host == 'localhost' or host.endswith(('.local', '.internal', '.lan')):
            return None
        try:
            if not ipaddress.ip_address(host).is_global:
                return None
        except ValueError:
            pass
        return value
    except (TypeError, ValueError):
        return None


def fetch_xml(url):
    request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT, 'Accept': 'application/rss+xml, application/xml, text/xml'})
    with urllib.request.urlopen(request, timeout=15) as response:
        body = response.read(MAX_RESPONSE_BYTES + 1)
    if len(body) > MAX_RESPONSE_BYTES:
        raise ValueError('feed response is too large')
    try:
        return ET.fromstring(body)
    except ET.ParseError as error:
        raise ValueError('invalid feed response') from error


def item_time(item):
    for name in ('pubDate', 'published', '{http://purl.org/dc/elements/1.1/}date'):
        value = item.findtext(name)
        if not value:
            continue
        try:
            return parsedate_to_datetime(value).timestamp()
        except (TypeError, ValueError, OverflowError):
            try:
                return datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()
            except ValueError:
                pass
    return 0


def parse_items(root, source=None, limit=10):
    results = []
    for item in root.findall('.//item'):
        title = clean_text(item.findtext('title'), 220)
        url = public_result_url((item.findtext('link') or '').strip())
        if not title or not url:
            continue
        published_timestamp = item_time(item)
        results.append({
            'title': title,
            'url': url,
            'excerpt': clean_text(item.findtext('description'), 420),
            'source': source or (urllib.parse.urlparse(url).hostname or '').removeprefix('www.'),
            'published_at': published_timestamp or None,
        })
        if len(results) >= limit:
            break
    return results


def search_web(query, limit=8):
    query = clean_text(query, 160)
    if not query:
        raise ValueError('search query is required')
    url = SEARCH_URL + '?' + urllib.parse.urlencode({'q': query, 'format': 'rss', 'count': limit})
    results = parse_items(fetch_xml(url), limit=limit)
    return {'ok': True, 'kind': 'search', 'query': query, 'updated_at': time.time(), 'count': len(results), 'results': results}


def news_headlines(limit=12):
    results = []
    for source, url in NEWS_FEEDS:
        try:
            results.extend(parse_items(fetch_xml(url), source=source, limit=limit))
        except (OSError, urllib.error.URLError, ET.ParseError, ValueError):
            continue
    unique = {}
    for result in results:
        unique.setdefault(result['url'], result)
    results = sorted(unique.values(), key=lambda result: result.get('published_at') or 0, reverse=True)[:limit]
    if not results:
        raise ValueError('news feeds are unavailable')
    return {'ok': True, 'kind': 'news', 'query': 'Latest headlines', 'updated_at': time.time(), 'count': len(results), 'results': results}


def save_results(path, payload):
    path = Path(path)
    with store_lock:
        try:
            document = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            document = {'news': None, 'search': None}
        document[payload['kind']] = payload
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(document, ensure_ascii=False) + '\n')
        temporary.replace(path)
    return payload


def load_results(path):
    try:
        document = json.loads(Path(path).read_text())
        if not isinstance(document, dict):
            raise ValueError
        return {'news': document.get('news'), 'search': document.get('search')}
    except (OSError, json.JSONDecodeError, ValueError):
        return {'news': None, 'search': None}


def format_discovery(payload):
    titles = [result['title'] for result in payload.get('results', [])[:3]]
    if not titles:
        return "I couldn't find any matching results, Sir."
    opening = f"I found {payload['count']} current headlines." if payload['kind'] == 'news' else f"I found {payload['count']} results for {payload['query']}."
    return opening + ' Top results: ' + '; '.join(titles) + '. The links and excerpts are saved under Explore in the Web UI.'
