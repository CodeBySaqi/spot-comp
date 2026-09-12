"""
Binance Spot Trading Competition — public data layer.

Everything here uses PUBLIC Binance endpoints (no API keys, no login):

  1. Competition detail (reward tiers, pools, cap, pairs, times)
       POST /bapi/composite/v1/public/growth-paas/resource/single
       body: {"code": "<competition code/slug>"}

  2. Activities under a competition (Main pool + Sprint rounds)
       POST /bapi/composite/v1/public/growth-paas/resource/list
       body: {"parentCode": "<competition code>", "pageSize": 30, "order": "id", "sort": "ASC"}

  3. Leaderboard (ranks, volumes, total users, total volume)
       POST /bapi/composite/v1/friendly/growth-paas/resource/summary/list
       body: {"resourceId": <activityId>, "pageIndex": 1, "pageSize": 100, "sort": "ASC", "order": "sequence"}

  4. Token price
       GET  https://data-api.binance.vision/api/v3/ticker/price?symbol=<TOKEN>USDT

These are the same endpoints the binance.com web app calls. They are unofficial
and may change or be rate-limited — this module is written defensively for that.
"""

import json
import re
import time

import requests

BAPI_HOST = "https://www.binance.com"
PRICE_HOST = "https://data-api.binance.vision"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "clienttype": "web",
    "lang": "en",
}

#: patterns used to resolve a token symbol (e.g. XPL) to a competition code
CODE_PATTERNS = [
    "spot-altcoin-festival-wave-{token}1",
    "spot-altcoin-festival-wave-{token}",
    "spot-altcoin-festival-wave-{token}2",
    "spot-altcoin-festival-wave-{token}3",
    "spot-altcoin-festival-wave-{token}-r1",
    "spot-altcoin-festival-wave-{token}-r2",
    "spot-altcoin-festival-wave-{token}-r3",
    "spot-trading-festival-wave-{token}1",
    "spot-trading-festival-wave-{token}",
    "spot-trading-festival-wave-{token}2",
    "spot-trading-festival-wave-{token}3",
    "spot-trading-festival-wave-{token}-r1",
    "spot-trading-festival-wave-{token}-r2",
    "spot-trading-festival-wave-{token}-r3",
    "{token}-trading-tournament",
    "{token}-trading-competition",
    "spot-{token}-trading-tournament",
]


class BinanceError(Exception):
    pass


class BinanceAPI:
    def __init__(self, timeout=30, retries=2, backoff=1.0, proxy=None, verbose=False):
        self.timeout = timeout
        self.retries = retries
        self.backoff = backoff
        self.verbose = verbose
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self._colo_cache = {}  # Cache for Colosseum page data
        if proxy:
            self.session.proxies = {"http": proxy, "https": proxy}

    # ------------------------------------------------------------------ http
    def _post(self, path, body):
        url = BAPI_HOST + path
        last_err = None
        for attempt in range(self.retries + 1):
            try:
                resp = self.session.post(url, data=json.dumps(body), timeout=self.timeout)
                if resp.status_code == 429:
                    last_err = BinanceError("rate limited (429)")
                    if self.verbose:
                        print(f"[bapi] 429 on {path}, retry {attempt+1}")
                    time.sleep(self.backoff * (attempt + 1))
                    continue
                resp.raise_for_status()
                data = resp.json()
                if data.get("success") is False or data.get("code") not in (None, "000000", "0", 0):
                    code = data.get("code")
                    msg = data.get("message")
                    if code in ("111002", "000002") or msg and "not found" in str(msg).lower():
                        return None
                    raise BinanceError(f"bapi error {code}: {msg}")
                return data.get("data")
            except requests.RequestException as e:
                last_err = e
                if self.verbose:
                    print(f"[bapi] {e} on {path}, retry {attempt+1}")
                time.sleep(self.backoff * (attempt + 1))
        raise BinanceError(f"request failed: {last_err}")

    def _get_json(self, url):
        for attempt in range(self.retries + 1):
            try:
                resp = self.session.get(url, timeout=self.timeout)
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as e:
                if attempt == self.retries:
                    raise BinanceError(f"request failed: {e}")
                time.sleep(self.backoff * (attempt + 1))

    # ------------------------------------------------------------- endpoints
    def resource_single(self, code):
        """Return the competition (activity group) dict for a code, or None."""
        return self._post("/bapi/composite/v1/public/growth-paas/resource/single",
                          {"code": code})

    def resource_list(self, parent_code, page_size=30):
        """Return list of activities (Main pool + sprint rounds) under a code."""
        data = self._post("/bapi/composite/v1/public/growth-paas/resource/list",
                          {"parentCode": parent_code, "pageSize": page_size,
                           "order": "id", "sort": "ASC"})
        if not data:
            return []
        return data.get("data") or []

    def leaderboard_page(self, resource_id, page_index=1, page_size=100):
        """One page of the leaderboard."""
        return self._post(
            "/bapi/composite/v1/friendly/growth-paas/resource/summary/list",
            {"resourceId": resource_id, "pageIndex": page_index,
             "pageSize": page_size, "sort": "ASC", "order": "sequence"})

    def token_price(self, symbol):
        """USD price of a token via the public market-data endpoint."""
        try:
            j = self._get_json(f"{PRICE_HOST}/api/v3/ticker/price?symbol={symbol.upper()}USDT")
            return float(j["price"])
        except (KeyError, TypeError, ValueError, BinanceError):
            try:
                j = self._get_json(f"{PRICE_HOST}/api/v3/ticker/price?symbol={symbol.upper()}USDC")
                return float(j["price"])
            except (KeyError, TypeError, ValueError, BinanceError):
                return None

    # -------------------------------------------------------------- helpers
    def resolve_competition(self, token_or_code):
        """Resolve a token symbol or a competition code to (group, activities).

        Returns (group_dict, [activity_dicts]) or (None, []).
        """
        token_or_code = (token_or_code or "").strip()
        if not token_or_code:
            return None, []

        low = token_or_code.lower()
        token = low.replace("/usdt", "").replace("/usdc", "").replace("/", "").strip()

        if "-" in low or "/" in low:
            try:
                group = self.resource_single(low)
            except Exception:
                group = None
            if group and group.get("type") == "TRADING_COMPETITION_ACTIVITY_GROUP":
                activities = self.resource_list(group.get("code") or low)
                activities = [a for a in activities
                              if a.get("globalContent", {}).get("productLine") == "SPOT_TRADING"
                              or a.get("type") == "TRADING_COMPETITION_ACTIVITY"]
                if activities:
                    return group, activities

        candidates = []
        if token:
            candidates += [p.format(token=token) for p in CODE_PATTERNS]
        candidates.append(low)

        seen = set()
        uniq = []
        for c in candidates:
            if c in seen:
                continue
            seen.add(c)
            uniq.append(c)

        results = []
        for code in uniq:
            group = self.resource_single(code)
            if not group:
                continue
            if group.get("type") != "TRADING_COMPETITION_ACTIVITY_GROUP":
                continue
            activities = self.resource_list(group.get("code") or code)
            activities = [a for a in activities
                          if a.get("globalContent", {}).get("productLine") == "SPOT_TRADING"
                          or a.get("type") == "TRADING_COMPETITION_ACTIVITY"]
            if not activities:
                continue
            results.append((group, activities))

        if not results:
            return None, []

        for group, activities in results:
            if group.get("status") == "PUBLISHED":
                return group, activities
        return results[0]


# ------------------------------------------------------------------ parsers
def flatten_rich_text(node, out, i18n=None):
    """Flatten Binance rich-text nodes into plain text chunks.

    `RichTextI18nKey` nodes hold an i18n key instead of literal text — resolve
    them via the `i18n` dict (from load_i18n) when provided.
    """
    if isinstance(node, dict):
        cfg = node.get("config")
        if isinstance(cfg, dict):
            content = cfg.get("content")
            if node.get("id") == "RichTextI18nKey" and isinstance(content, str):
                out.append((i18n or {}).get(content, content))
            elif isinstance(content, str):
                out.append(content)
            elif isinstance(content, (list, dict)):
                flatten_rich_text(content, out, i18n)
        for v in node.values():
            flatten_rich_text(v, out, i18n)
    elif isinstance(node, list):
        for v in node:
            flatten_rich_text(v, out, i18n)


def rich_text_to_text(raw, i18n=None):
    """Convert a rich-text structure (dict or JSON string) to plain text,
    resolving i18n keys."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (TypeError, ValueError):
            return raw
    chunks = []
    flatten_rich_text(raw, chunks, i18n)
    return "".join(chunks)


def group_rule_text(group, i18n=None):
    """Plain text of the competition's rules (contains the tail cap)."""
    rule = (group.get("i18nContent", {}).get("homepage", {}) or {}).get("ruleContent") or {}
    raw = rule.get("rule") or ""
    if raw:
        try:
            node = json.loads(raw)
        except (TypeError, ValueError):
            node = None
        if node is not None:
            chunks = []
            flatten_rich_text(node, chunks, i18n)
            return "".join(chunks)
        texts = re.findall(r'"content":"((?:[^"\\]|\\.)*)"', raw)
        return "".join(t.encode("utf-8").decode("unicode_escape", "ignore") for t in texts)
    chunks = []
    flatten_rich_text(rule, chunks, i18n)
    return "".join(chunks)


#: Binance frontend i18n resources (English) — hold the real campaign texts
#: that the bapi serves as untranslated "gro-*" keys.
I18N_RESOURCE_URLS = [
    "https://bin.bnbstatic.com/api/i18n/-/web/cms/en/growth-platform",
    "https://bin.bnbstatic.com/api/i18n/-/web/cms/en/activity-ui",
]

_i18n = {"ts": 0.0, "data": {}}
_I18N_TTL = 24 * 3600


def load_i18n(force=False):
    """Load Binance's frontend i18n resources → flat {key: text} dict.

    Cached in memory for 24h. Returns {} on failure (never raises).
    """
    global _i18n
    now = time.time()
    if not force and _i18n.get("data") and (now - _i18n.get("ts", 0)) < _I18N_TTL:
        return _i18n["data"]
    merged = {}
    for url in I18N_RESOURCE_URLS:
        try:
            resp = requests.get(url, timeout=30,
                                headers={"User-Agent": HEADERS["User-Agent"]})
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict):
                merged.update(data)
        except Exception:
            continue
    if merged:
        _i18n = {"ts": now, "data": merged}
    return merged


def tail_cap_from_text(text, prefer_unit=None):
    """Extract the per-user cap from competition rules text.

    Handles multiple patterns:
      - "capped at 500 XPL per user"
      - "maximum of 500 XPL per user"
      - "max 500 XPL per user"
      - "up to 500 XPL"
      - "cap of 500 XPL"
      - "limit of 500 XPL per user"

    When `prefer_unit` is given (e.g. "BNB"), a match whose token matches that
    unit wins over earlier matches (so a sprint-round cap doesn't shadow the
    main-pool cap). Returns (amount, token_symbol) or (None, None).
    """
    if not text:
        return None, None

    patterns = [
        # "capped at 500 XPL" / "capped at 500.00 XPL"
        r"capped\s+at\s*([\d][\d,.]*)\s*([A-Za-z][A-Za-z0-9]*)",
        # "maximum of 500 XPL" / "maximum 500 XPL"
        r"maximum\s+(?:of\s+)?([\d][\d,.]*)\s*([A-Za-z][A-Za-z0-9]*)",
        # "max 500 XPL" / "max of 500 XPL"
        r"\bmax(?:imum)?\s+(?:of\s+)?([\d][\d,.]*)\s*([A-Za-z][A-Za-z0-9]*)",
        # "cap of 500 XPL" / "cap at 500 XPL"
        r"\bcap\s+(?:of|at)\s+([\d][\d,.]*)\s*([A-Za-z][A-Za-z0-9]*)",
        # "up to 500 XPL per user"
        r"up\s+to\s+([\d][\d,.]*)\s*([A-Za-z][A-Za-z0-9]*)\s+(?:per\s+user|each|per\s+participant)",
        # "limit of 500 XPL"
        r"limit\s+(?:of\s+)?([\d][\d,.]*)\s*([A-Za-z][A-Za-z0-9]*)",
    ]

    matches = []
    for pattern in patterns:
        for m in re.finditer(pattern, text, re.I):
            amount = float(m.group(1).replace(",", ""))
            token = m.group(2).upper()
            matches.append((amount, token))

    if not matches:
        return None, None

    if prefer_unit:
        pu = prefer_unit.upper()
        for amount, token in matches:
            if token == pu:
                return amount, token

    return matches[0]


_I18N_KEY_RE = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)+$")


def is_i18n_key(s):
    """True if a string looks like an untranslated Binance i18n key.

    e.g. "gro-202609tls4-homepage-banner-title" (lowercase + digits + dashes,
    no spaces). Real titles have spaces / capitals / other punctuation.
    """
    return bool(s) and " " not in s and bool(_I18N_KEY_RE.match(s))
