"""
List running Binance Spot campaigns — from the official Spot Colosseum page.

Binance's "Spot Colosseum" hub (https://www.binance.com/en/events/spot-colosseum)
is the single source of truth: it lists every currently-running spot campaign
with its title, prize and end time. New campaigns appear there automatically.

The page's HTML is WAF/region protected for plain HTTP clients, so we read its
rendered content through the r.jina.ai reader (requires a free API key).
Multiple fallback strategies are included for resilience.

SETUP:
  1. Get a free Jina Reader API key at https://jina.ai/reader (1000 req/month free)
  2. Set it in config.json as "jina_api_key": "jina_xxxxxxxx"
     OR set the environment variable SPOTCOMP_JINA_KEY=jina_xxxxxxxx
"""

import json
import os
import re
import time

import requests

from binance_api import is_i18n_key

COLOSSEUM_URL = "https://www.binance.com/en/events/spot-colosseum"

# Cache file for last-known-good campaign list
CACHE_FILE = os.environ.get("SPOTCOMP_CACHE_FILE", "campaigns_cache.json")
CACHE_MAX_AGE_SECONDS = 60 * 60 * 12  # 12 hours

# Jina Reader API key — loaded from env var or set by bot.py from config.json
JINA_API_KEY = os.environ.get("SPOTCOMP_JINA_KEY", "")

# HTTP proxy for all outbound requests (set by bot.py from config.json)
PROXY = os.environ.get("SPOTCOMP_PROXY", "")

#: extract campaign links out of the rendered colosseum markdown
LINK_RE = re.compile(
    r'\[!\[[^\]]*\]\([^)]*\)\s*([^\]]+)\]'
    r'\(https://www\.binance\.com/activity/trading-competition/([A-Za-z0-9/_-]+)\)'
)
TOKEN_RE = re.compile(r'([A-Z]{2,12})\s+Token')
PRIZE_RE = re.compile(r'([\d,]+(?:\.\d+)?\s*[A-Z]{2,12})')
ENDS_RE = re.compile(r'Ends at\s+([\d-]+ [\d:]+)')

GENERIC_LINK_RE = re.compile(
    r'https://www\.binance\.com/activity/trading-competition/([A-Za-z0-9/_-]+)'
)


class Campaign:
    def __init__(self, code, token=None, title=None, prize=None, ends_ms=None,
                 status=None, source="colosseum"):
        self.code = code
        self.token = (token or "?").upper()
        self.title = title
        self.prize = prize
        self.ends_ms = ends_ms
        self.status = status
        self.source = source

    def to_dict(self):
        return {
            "code": self.code,
            "token": self.token,
            "title": self.title,
            "prize": self.prize,
            "ends_ms": self.ends_ms,
            "status": self.status,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, d):
        return cls(**d)


def set_jina_key(key):
    """Allow bot.py to set the Jina key from config.json at startup."""
    global JINA_API_KEY
    if key:
        JINA_API_KEY = key


def set_proxy(proxy_url):
    """Allow bot.py to set an HTTP proxy from config.json at startup."""
    global PROXY
    PROXY = proxy_url or ""


def _get_proxies():
    """Return a requests-compatible proxies dict using the configured proxy."""
    if PROXY:
        return {"http": PROXY, "https": PROXY}
    return None


# ============================================================ CACHE HELPERS
def _save_cache(campaigns):
    """Persist a successful campaign list to disk for fallback use."""
    try:
        data = {
            "ts": int(time.time()),
            "campaigns": [c.to_dict() for c in campaigns],
        }
        with open(CACHE_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception:
        pass


def _load_cache(max_age_seconds=None):
    """Load cached campaign list if it exists and is recent enough."""
    if max_age_seconds is None:
        max_age_seconds = CACHE_MAX_AGE_SECONDS
    try:
        with open(CACHE_FILE, "r") as f:
            data = json.load(f)
        age = int(time.time()) - data.get("ts", 0)
        if age > max_age_seconds:
            return None
        return [Campaign.from_dict(d) for d in data.get("campaigns", [])]
    except Exception:
        return None


# ================================================ FETCH STRATEGIES
def _fetch_via_jina(timeout=30):
    """Fetch via r.jina.ai reader WITH API key.

    Jina Reader requires an API key (free tier: 1000 req/month).
    Get yours at: https://jina.ai/reader
    """
    if not JINA_API_KEY:
        return None  # skip — no key configured

    reader_url = "https://r.jina.ai/" + COLOSSEUM_URL
    headers = {
        "Authorization": f"Bearer {JINA_API_KEY}",
        "Accept": "text/markdown, text/plain, */*",
        "X-Return-Format": "markdown",
        "X-With-Generated-Alt": "true",
        "X-Locale": "en-US",
        "X-Target-Selector": "body",
    }
    resp = requests.get(reader_url, timeout=timeout, headers=headers,
                        proxies=_get_proxies())
    resp.raise_for_status()
    text = resp.text
    if "Compliance error" not in text and "trading-competition/" in text:
        return text
    return None


def _fetch_via_jina_free(timeout=30):
    """Try Jina without auth (in case they still allow some free requests)."""
    reader_url = "https://r.jina.ai/" + COLOSSEUM_URL
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; SpotCompBot/1.0)",
        "Accept": "text/markdown, text/plain, */*",
        "X-Return-Format": "markdown",
        "X-With-Generated-Alt": "true",
    }
    resp = requests.get(reader_url, timeout=timeout, headers=headers,
                        proxies=_get_proxies())
    if resp.status_code == 401:
        return None  # API key required
    resp.raise_for_status()
    text = resp.text
    if "Compliance error" not in text and "trading-competition/" in text:
        return text
    return None


def _fetch_direct(timeout=30):
    """Try fetching the Colosseum page directly with full browser headers.

    This works on many VPS IPs that aren't in Binance's blocklist.
    Cloudflare may still challenge, but it's worth trying.
    """
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0",
        "Referer": "https://www.binance.com/en/events",
        "lang": "en",
        "clienttype": "web",
    }
    resp = requests.get(COLOSSEUM_URL, timeout=timeout, headers=headers,
                        allow_redirects=True, proxies=_get_proxies())
    resp.raise_for_status()
    text = resp.text
    if ("trading-competition/" in text
            and "challenge" not in text.lower()
            and "Compliance error" not in text
            and len(text) > 2000):
        return text
    return None


def _fetch_via_allorigins(timeout=30):
    """Fetch via allorigins.win CORS proxy."""
    url = f"https://api.allorigins.win/raw?url={COLOSSEUM_URL}"
    resp = requests.get(url, timeout=timeout,
                        headers={"User-Agent": "Mozilla/5.0"},
                        proxies=_get_proxies())
    resp.raise_for_status()
    text = resp.text
    if "trading-competition/" in text and len(text) > 2000:
        return text
    return None


def _fetch_via_google_cache(timeout=30):
    """Fetch via Google's web cache."""
    cache_url = f"https://webcache.googleusercontent.com/search?q=cache:{COLOSSEUM_URL}"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        ),
    }
    resp = requests.get(cache_url, timeout=timeout, headers=headers,
                        proxies=_get_proxies())
    resp.raise_for_status()
    text = resp.text
    if "trading-competition/" in text:
        return text
    return None


def fetch_colosseum_content(timeout=30):
    """Try multiple strategies to fetch the Colosseum page content.

    Returns (content_text, strategy_name) or raises RuntimeError if all fail.

    Order:
      1. Jina with API key (most reliable — set SPOTCOMP_JINA_KEY env var
         or call set_jina_key() from bot.py after reading config.json)
      2. Jina free tier (sometimes works without a key)
      3. Direct fetch with browser headers (works on many VPS IPs)
      4. AllOrigins CORS proxy
      5. Google web cache
    """
    strategies = [
        ("jina_with_key", _fetch_via_jina),
        ("jina_free", _fetch_via_jina_free),
        ("direct", _fetch_direct),
        ("allorigins", _fetch_via_allorigins),
        ("google_cache", _fetch_via_google_cache),
    ]

    errors = []
    for name, fetcher in strategies:
        try:
            content = fetcher(timeout=timeout)
            if content:
                return content, name
        except Exception as e:
            errors.append(f"{name}: {e}")
        time.sleep(0.5)

    error_summary = "; ".join(errors[-3:])
    raise RuntimeError(
        f"All fetch strategies failed for Colosseum page. "
        f"Set SPOTCOMP_JINA_KEY env var or add 'jina_api_key' to config.json "
        f"(free key at jina.ai/reader). Errors: {error_summary}"
    )


# ------------------------------------------------------------- colosseum parse
def _code_of_path(path):
    """Return the competition group code for a captured URL path.

    Nested URLs like "202609tradersleague4/Spot-Carnival-Waves-Round1" resolve
    to the FIRST segment (the activity-group code). Flat codes pass through.
    """
    return path.split("/", 1)[0]


def parse_colosseum(markdown):
    """Parse campaign entries out of the colosseum markdown/html.

    Uses the primary link pattern; falls back to a looser match over any
    trading-competition URL so a layout change doesn't silently empty the list.
    """
    entries = []
    seen = set()
    for m in LINK_RE.finditer(markdown):
        text = re.sub(r"\s+", " ", m.group(1)).strip()
        code = _code_of_path(m.group(2))
        if code.lower() in seen:
            continue
        seen.add(code.lower())
        token = None
        tm = TOKEN_RE.search(text)
        if tm:
            token = tm.group(1)
        pm = PRIZE_RE.search(text)
        prize = pm.group(1) if pm else None
        em = ENDS_RE.search(text)
        ends = em.group(1) if em else None
        entries.append({"code": code, "token": token, "prize": prize,
                        "ends_str": ends, "title_raw": text})

    if not entries:
        # fallback: any campaign URL; token/title get filled in later by enrich()
        for m in GENERIC_LINK_RE.finditer(markdown):
            code = _code_of_path(m.group(1))
            if code.lower() in seen:
                continue
            seen.add(code.lower())
            s = max(0, m.start() - 700)
            window = markdown[s:m.start()]
            idx = window.rfind("](")
            text = window[idx + 2:].strip() if idx != -1 else ""
            token = None
            tm = TOKEN_RE.search(text)
            if tm:
                token = tm.group(1)
            entries.append({"code": code, "token": token, "prize": None,
                            "ends_str": None, "title_raw": text})
    return entries


def colosseum_entries(timeout=30):
    """Fetch + parse the Colosseum page → list of raw entry dicts."""
    content, strategy = fetch_colosseum_content(timeout=timeout)
    entries = parse_colosseum(content)
    return entries


# ------------------------------------------------------------------- bapi
def enrich(api, entry):
    """Resolve a code via bapi and build a Campaign."""
    code = entry.get("code")
    token = entry.get("token")
    # clean the raw link text: drop trailing "Ends at ... Ongoing/Expired" junk
    title = (entry.get("title_raw") or "").strip()
    title = re.split(r"\b[Ee]nds at\b", title)[0].strip() or None
    prize = entry.get("prize")
    ends_ms = None
    status = None

    # ALWAYS try to extract the competition token from the code first
    # e.g. "spot-altcoin-festival-wave-ENSO1" → "ENSO"
    #       "spot-trading-festival-wave-r3" → "r3"
    code_token = None
    cm = re.search(r'wave-([A-Za-z0-9]+?)(\d*)$', code or "")
    if cm:
        code_token = cm.group(1).upper()

    try:
        group = api.resource_single(code)
    except Exception:
        group = None
    if group:
        try:
            hp = (group.get("i18nContent") or {}).get("homepage") or {}
            hero = hp.get("heroBannerContent") or {}
            t = (hero.get("title") or hp.get("title") or "").strip()
            # only accept a real title; ignore untranslated i18n keys like
            # "gro-202609tls4-homepage-banner-title"
            if t and t.lower() != "null" and not is_i18n_key(t):
                title = t
            pci = hp.get("prizePoolInformationContent") or {}
            tp = (pci.get("totalPrizeAmount") or "").strip()
            if tp:
                prize = tp
            ends_ms = group.get("unpublishedTime")
            status = group.get("status")

            # Try to get the actual token from trading pairs
            pairs = (hp.get("includeSpotTradingPairList")
                     or hp.get("includeTradingPairList") or [])
            if pairs:
                # e.g. ["ENSO/USDT", "ENSO/USDC"] → "ENSO"
                first_pair = pairs[0] if pairs else ""
                pm2 = re.match(r'^([A-Z]{2,12})/', first_pair)
                if pm2:
                    code_token = pm2.group(1)
        except Exception:
            pass

    # Priority: code-derived token > trading pair token > parsed token > prize token
    if code_token and code_token != "?":
        token = code_token
    elif not token or token == "?":
        # Last resort: extract from prize string
        pm = re.search(r'([A-Z]{2,12})\s*$', prize or "")
        if pm:
            token = pm.group(1)

    return Campaign(code=code, token=token, title=title, prize=prize,
                    ends_ms=ends_ms, status=status)


def list_running_campaigns(api):
    """All currently-running spot campaigns.

    Tries:
      1. Colosseum page via multiple fetch strategies (Jina w/ key, direct, etc.)
      2. Cached last-known-good result (if all fetching fails)

    Returns a list of Campaign objects sorted by end time (soonest first).
    Raises RuntimeError only if ALL strategies (including cache) fail.
    """
    last_error = None

    # --- Strategy 1: Fetch Colosseum page ---
    try:
        entries = colosseum_entries()
        if entries:
            camps = [enrich(api, e) for e in entries]
            running = [c for c in camps if c.status is None or c.status == "PUBLISHED"]
            running.sort(key=lambda c: (c.ends_ms is None, c.ends_ms or 0))
            if running:
                _save_cache(running)
                return running
    except Exception as e:
        last_error = e

    # --- Strategy 2: Cache fallback ---
    cached = _load_cache()
    if cached:
        running = [c for c in cached if c.status is None or c.status == "PUBLISHED"]
        if running:
            return running

    raise RuntimeError(
        f"Could not fetch campaigns from any source: {last_error}"
    )

