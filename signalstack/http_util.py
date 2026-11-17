"""Polite HTTP fetching.

Rules enforced here (brief §5 / §14):
- Only public URLs; never any authentication or paywall bypass.
- robots.txt is checked before fetching ordinary web pages (RSS feeds are
  publisher-syndication endpoints and are fetched directly).
- Per-host rate limiting, a descriptive User-Agent, hard timeouts.
- Every failure is returned as data (never silently swallowed) so crawl logs
  and the monthly audit can show exactly what blocked.
"""
import hashlib
import time
import urllib.robotparser
from urllib.parse import urlparse

import requests

from . import config

_last_hit = {}
_robots_cache = {}


def _polite(host):
    last = _last_hit.get(host, 0)
    wait = config.SAME_HOST_DELAY - (time.time() - last)
    if wait > 0:
        time.sleep(wait)
    _last_hit[host] = time.time()


def robots_allowed(url):
    """True if robots.txt permits our UA to fetch this web page.

    The robots.txt body is fetched with our own UA (some CDNs 403 the
    default urllib UA, which RobotFileParser.read() would misread as a
    blanket disallow) and parsed locally."""
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    if base not in _robots_cache:
        rp = urllib.robotparser.RobotFileParser()
        try:
            r = requests.get(base + "/robots.txt",
                             headers={"User-Agent": config.USER_AGENT}, timeout=10)
            if r.status_code == 200:
                rp.parse(r.text.splitlines())
            elif r.status_code in (401, 403):
                rp.disallow_all = True  # RFC 9309: auth-blocked robots = disallow all
            else:
                rp = None  # 404 etc. -> no restrictions published
        except Exception:
            rp = None  # unreachable robots.txt -> treat as allowed, page fetch decides
        _robots_cache[base] = rp
    rp = _robots_cache[base]
    if rp is None:
        return True
    return rp.can_fetch("SignalStack", url)


def fetch(url, check_robots=False, timeout=None):
    """GET a URL. Returns dict: ok, status, text, error, final_url."""
    parsed = urlparse(url)
    if check_robots and not robots_allowed(url):
        return {"ok": False, "status": None, "text": "", "final_url": url,
                "error": "blocked by robots.txt"}
    _polite(parsed.netloc)
    try:
        r = requests.get(url, headers={"User-Agent": config.USER_AGENT},
                         timeout=timeout or config.REQUEST_TIMEOUT, allow_redirects=True)
        return {"ok": r.status_code == 200, "status": r.status_code,
                "text": r.text if r.status_code == 200 else "",
                "final_url": r.url, "error": "" if r.status_code == 200 else f"HTTP {r.status_code}"}
    except requests.RequestException as e:
        return {"ok": False, "status": None, "text": "", "final_url": url,
                "error": f"{type(e).__name__}: {e}"[:200]}


def content_hash(text):
    return hashlib.sha256(" ".join(text.split()).encode("utf-8", "ignore")).hexdigest()


def domain_of(url):
    return urlparse(url).netloc.lower().replace("www.", "")
