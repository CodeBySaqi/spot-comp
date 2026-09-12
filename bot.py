#!/usr/bin/env python3
"""
Binance Spot Competition → Telegram bot.

Scrapes Binance's public spot-trading-competition endpoints and posts a
"Rank 1001+ proportional share" estimator card for each watched competition,
plus auto-detects new campaigns.

Runs with ONLY the `requests` library. Uses Telegram long-polling (no webhook).

Commands:
  /spotcomp XPL      -> full card for that token / competition code
  /campaigns         -> all running spot campaigns (with clickable buttons)
  /comps             -> one-line status of every watched competition
  /watch XPL         -> start tracking a token or code
  /unwatch XPL       -> stop tracking
  /now               -> refresh + post cards right now (channel + chat)
  /help
"""

import argparse
import json
import os
import threading
import time
import traceback

import requests

from binance_api import BinanceAPI
from cards import (build_card, build_campaigns_message, build_multi_card,
                   build_summary_line, build_tracks_message, compute,
                   compute_all_tracks, esc, identify_tracks, title_for,
                   volume_fingerprint)
from campaigns import (Campaign, list_running_campaigns, colosseum_entries,
                       enrich, set_proxy, set_jina_key)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
WATCHLIST_PATH = os.path.join(BASE_DIR, "watchlist.json")
STATE_PATH = os.path.join(BASE_DIR, "state.json")

DEFAULT_CONFIG = {
    "bot_token": "",
    "channel_id": "",
    "refresh_minutes": 15,
    "watchlist": ["PYTH", "RE"],
    "announce_new": True,
    "post_on_update_only": True,
    "auto_remove_ended": True,
    "track_all_running": True,
    "campaigns_cache_minutes": 30,
    "post_first_run": False,
    "proxy": "",
    "binance_verbose": False,
    "jina_api_key": "",
    "example_volumes": [60000, 30000, 10000, 5000, 1000],
}

TG = "https://api.telegram.org"


# --------------------------------------------------------------------- state
def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return default


def save_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


class Config:
    def __init__(self):
        data = load_json(CONFIG_PATH, {})
        self.cfg = {**DEFAULT_CONFIG, **data}
        self.watchlist = load_json(WATCHLIST_PATH, None)
        if not isinstance(self.watchlist, list):
            self.watchlist = list(self.cfg.get("watchlist") or [])
        self.state = load_json(STATE_PATH, {})

    def save_watchlist(self):
        save_json(WATCHLIST_PATH, self.watchlist)

    def save_state(self):
        save_json(STATE_PATH, self.state)


# ------------------------------------------------------------------ telegram
class Telegram:
    def __init__(self, token):
        self.token = token
        self._local = threading.local()

    @property
    def session(self):
        s = getattr(self._local, "s", None)
        if s is None:
            s = requests.Session()
            self._local.s = s
        return s

    def call(self, method, **params):
        last = None
        for attempt in range(4):
            try:
                r = self.session.post(f"{TG}/bot{self.token}/{method}",
                                      data=params, timeout=35)
            except requests.RequestException as e:
                last = e
                time.sleep(2 * (attempt + 1))
                continue
            if r.status_code == 429:
                try:
                    ra = r.json().get("parameters", {}).get("retry_after", 3)
                except ValueError:
                    ra = 3
                time.sleep(int(ra) + 1)
                last = RuntimeError("429")
                continue
            if r.status_code >= 500:
                time.sleep(2 * (attempt + 1))
                last = RuntimeError(f"HTTP {r.status_code}")
                continue
            r.raise_for_status()
            j = r.json()
            if not j.get("ok"):
                raise RuntimeError(f"Telegram error: {j}")
            return j.get("result")
        raise RuntimeError(f"Telegram {method} failed: {last}")

    @staticmethod
    def _chunks(text, limit=4000):
        text = text.strip()
        while text:
            if len(text) <= limit:
                yield text
                break
            cut = text.rfind("\n", 0, limit)
            if cut < 200:
                cut = limit
            yield text[:cut]
            text = text[cut:].lstrip("\n")

    def send(self, chat_id, text, reply_markup=None):
        for chunk in self._chunks(text):
            params = dict(chat_id=chat_id, text=chunk,
                          parse_mode="HTML", disable_web_page_preview=True)
            if reply_markup:
                params["reply_markup"] = reply_markup
            self.call("sendMessage", **params)

    def answer_callback(self, callback_query_id, text=""):
        try:
            self.call("answerCallbackQuery", callback_query_id=callback_query_id,
                      text=text, show_alert=False)
        except Exception:
            pass

    def get_updates(self, offset, timeout=25):
        return self.call("getUpdates", offset=offset, timeout=timeout,
                         allowed_updates=json.dumps(["message", "callback_query"]))


# ------------------------------------------------------------------- engine
class Engine:
    def __init__(self, cfg: Config, api: BinanceAPI, tg: Telegram, log=print):
        self.cfg = cfg
        self.api = api
        self.tg = tg
        self.log = log
        self.lock = threading.Lock()

    @staticmethod
    def _norm(item):
        return str(item or "").strip().lower()

    def watchlist_has(self, item):
        key = self._norm(item)
        return any(self._norm(w) == key for w in self.cfg.watchlist)

    def _code_of(self, item):
        key = self._norm(item)
        cache = self.cfg.state.get("code_cache") or {}
        hit = cache.get(key)
        if hit and hit.get("ts", 0) > time.time() - 86400:
            return hit.get("code")
        code, _ = self._resolve_of(item)
        if code:
            with self.lock:
                cc = self.cfg.state.setdefault("code_cache", {})
                cc[key] = {"code": code, "ts": int(time.time())}
                self.cfg.save_state()
        return code

    def _resolve_of(self, item):
        try:
            group, _ = self.api.resolve_competition(item)
        except Exception:
            group = None
        if not group:
            return None, None
        return self._norm(group.get("code")), group.get("status")

    def refresh_one(self, item):
        group, activities = self.api.resolve_competition(item)
        if not group:
            return None
        stats = compute(self.api, group, activities)
        if stats:
            ev = self.cfg.cfg.get("example_volumes") or (60000, 30000, 10000, 5000, 1000)
            try:
                ev = [int(v) for v in ev]
            except (TypeError, ValueError):
                ev = (60000, 30000, 10000, 5000, 1000)
            stats["example_volumes"] = list(ev)
        return stats

    def refresh_tracks(self, item):
        """Resolve a competition → track entries (Spot/bStock/TradFi/Futures)."""
        group, activities = self.api.resolve_competition(item)
        if not group:
            return None
        ev = self.cfg.cfg.get("example_volumes") or (60000, 30000, 10000, 5000, 1000)
        try:
            ev = [int(v) for v in ev]
        except (TypeError, ValueError):
            ev = (60000, 30000, 10000, 5000, 1000)
        entries = compute_all_tracks(self.api, group, activities)
        for e in entries:
            if e["kind"] == "single":
                e["stats"]["example_volumes"] = list(ev)
            else:
                for s in e["stats_list"]:
                    s["example_volumes"] = list(ev)
        return entries

    def refresh_all(self):
        out, seen = [], set()
        items = list(self.cfg.watchlist)
        for i, item in enumerate(items):
            try:
                stats = self.refresh_one(item)
            except Exception as e:
                self.log(f"[warn] refresh '{item}' failed: {e}")
                stats = None
            if not stats:
                self.log(f"[warn] could not resolve '{item}'")
            else:
                ckey = self._norm((stats.get("group") or {}).get("code") or item)
                if ckey not in seen:
                    seen.add(ckey)
                    out.append((item, stats))
                    with self.lock:
                        cc = self.cfg.state.setdefault("code_cache", {})
                        cc[self._norm(item)] = {"code": ckey, "ts": int(time.time())}
                        self.cfg.save_state()
            if i < len(items) - 1:
                time.sleep(0.4)
        return out

    def _watches(self, camp):
        code = self._norm(camp.code)
        token = self._norm(camp.token) if camp.token else None
        for w in self.cfg.watchlist:
            wl = self._norm(w)
            if wl == code or (token and wl == token):
                return True
        return False

    def _dedupe_watchlist(self):
        ded, seen = [], set()
        for w in self.cfg.watchlist:
            k = self._norm(w)
            if k and k not in seen:
                seen.add(k)
                ded.append(w)
        self.cfg.watchlist = ded

    def sync_running_campaigns(self):
        track_all = self.cfg.cfg.get("track_all_running", True)
        try:
            entries = colosseum_entries()
        except Exception as e:
            self.log(f"[warn] campaign sync failed: {e}")
            return []
        entries = [e for e in entries if e.get("code")]
        if not entries:
            return []

        running = []
        for e in entries:
            try:
                camp = enrich(self.api, e)
            except Exception:
                camp = None
            if camp is not None and (camp.status == "PUBLISHED"
                                     or (camp.status is None and camp.title)):
                running.append(camp)
            time.sleep(0.2)

        running_codes = [c.code for c in running]

        with self.lock:
            state = self.cfg.state
            prev_seen = {str(k).lower() for k in (state.get("seen_campaigns") or [])}

            if not running_codes and prev_seen:
                self.log("[sync] Colosseum returned 0 running campaigns — skipping "
                         "state update (likely blocked/partial fetch)")
                return []

            excluded = {str(k).lower() for k in (state.get("excluded_codes") or [])}

            if "seen_campaigns" not in state:
                state["seen_campaigns"] = [c.lower() for c in running_codes]
                state["announced_campaigns"] = [c.lower() for c in running_codes]
                if track_all:
                    adopted = 0
                    for c in running:
                        ck = c.code.lower()
                        if ck in excluded or self._watches(c):
                            continue
                        self.cfg.watchlist.append(c.code)
                        adopted += 1
                    self._dedupe_watchlist()
                    self.cfg.save_watchlist()
                    self.log(f"[sync] baseline: auto-tracking {adopted} running campaign(s)")
                self.cfg.save_state()
                return []

            seen = {str(k).lower() for k in (state.get("seen_campaigns") or [])}
            announced = {str(k).lower() for k in (state.get("announced_campaigns") or [])}
            now_codes = {c.lower() for c in running_codes}

            if track_all:
                for c in running:
                    ck = c.code.lower()
                    if ck in excluded or self._watches(c):
                        continue
                    self.cfg.watchlist.append(c.code)
                self._dedupe_watchlist()

            announce_now = []
            for c in running:
                ck = c.code.lower()
                if ck in excluded or ck in seen or ck in announced:
                    continue
                announce_now.append(c.code)
                announced.add(ck)

            state["seen_campaigns"] = sorted(now_codes)
            state["announced_campaigns"] = sorted(announced)
            self.cfg.save_watchlist()
            self.cfg.save_state()

        return announce_now

    def get_campaigns(self, force=False):
        with self.lock:
            cache = self.cfg.state.get("campaigns_cache", {})
            now = int(time.time())
            ttl = int(self.cfg.cfg.get("campaigns_cache_minutes", 30) or 30) * 60
            if not force and cache.get("ts") and (now - cache["ts"]) < ttl:
                return [Campaign.from_dict(d) for d in cache.get("campaigns", [])]

        try:
            camps = list_running_campaigns(self.api)
        except Exception as e:
            with self.lock:
                cached = self.cfg.state.get("campaigns_cache", {}).get("campaigns")
            if cached:
                self.log(f"[warn] colosseum fetch failed, serving cached list: {e}")
                return [Campaign.from_dict(d) for d in cached]
            raise

        with self.lock:
            self.cfg.state["campaigns_cache"] = {
                "ts": int(time.time()),
                "campaigns": [c.to_dict() for c in camps],
            }
            self.cfg.save_state()
        return camps

    def post_card(self, stats, chat_id=None, extra_chat=None):
        card = build_card(stats)
        targets, sent = [], set()
        for t in (self.cfg.cfg.get("channel_id"), chat_id, extra_chat):
            if t and str(t) not in sent:
                targets.append(t)
                sent.add(str(t))
        for t in targets:
            self.tg.send(t, card)
        return card

    def post_update_cycle(self, force=False, extra_chat=None):
        new = self.sync_running_campaigns()
        if new and self.cfg.cfg.get("announce_new"):
            ch = self.cfg.cfg.get("channel_id")
            if ch:
                try:
                    self.tg.send(ch, "🆕 New competition(s) detected:\n" +
                                 "\n".join(f"• /spotcomp {c}" for c in new))
                except Exception as e:
                    self.log(f"[warn] announce-new failed: {e}")

        items = self.refresh_all()
        with self.lock:
            cards = self._post_cycle_locked(force, items, extra_chat)
        return len(new), cards

    def _post_cycle_locked(self, force, items, extra_chat=None):
        cards, posted = [], set()
        post_first = self.cfg.cfg.get("post_first_run", False)
        for item, stats in items:
            group = stats.get("group") or {}
            code = (group.get("code") or item or "").strip()
            ckey = code.lower()
            if not ckey or ckey in posted:
                continue
            posted.add(ckey)
            if stats.get("ended"):
                self._handle_ended(item, stats)
                continue
            fp = volume_fingerprint(stats)
            key = f"volfp:{ckey}"
            last = self.cfg.state.get(key)
            volume_changed = (last is not None and last != fp)
            first_seen = (last is None)
            should_post = (force or volume_changed
                           or (first_seen and post_first)
                           or not self.cfg.cfg.get("post_on_update_only"))
            if should_post:
                try:
                    card = self.post_card(stats, extra_chat=extra_chat)
                    cards.append(card)
                    self.cfg.state[key] = fp
                    self.cfg.state[f"last_post:{ckey}"] = int(time.time())
                    self.cfg.save_state()
                    self.log(f"[post] {ckey} — card sent")
                except Exception as e:
                    self.log(f"[warn] post '{ckey}' failed: {e}")
            else:
                self.cfg.state[key] = fp
                self.cfg.save_state()
        return cards

    def _handle_ended(self, item, stats):
        if not self.cfg.cfg.get("auto_remove_ended", True):
            return
        title = ((stats.get("group") or {}).get("i18nContent", {}) or {}) \
            .get("homepage", {}).get("heroBannerContent", {}).get("title") or item
        code = self._norm((stats.get("group") or {}).get("code"))
        if self._remove_from_watchlist(item, code=code or None):
            with self.lock:
                if code:
                    self.cfg.state.pop(f"volfp:{code}", None)
                    self.cfg.state.pop(f"last_post:{code}", None)
                self.cfg.save_state()
            self.log(f"[watch] {item} ended — removed from watchlist")
            if self.cfg.cfg.get("announce_new"):
                ch = self.cfg.cfg.get("channel_id")
                if ch:
                    try:
                        self.tg.send(ch, f"🏁 <b>{esc(title)}</b> has ended — "
                                         f"removed from the watchlist.")
                    except Exception as e:
                        self.log(f"[warn] announce-ended failed: {e}")

    def _remove_from_watchlist(self, item, code=None):
        if code is None:
            code = self._code_of(item)
        keep, removed = [], False
        for w in list(self.cfg.watchlist):
            wl = self._norm(w)
            if wl == self._norm(item) or (code and wl == code):
                removed = True
            else:
                keep.append(w)
        if removed:
            self.cfg.watchlist = keep
            self.cfg.save_watchlist()
        return removed

    def loop(self):
        interval = max(1, int(self.cfg.cfg.get("refresh_minutes", 15) or 15))
        self.log(f"refresh loop every {interval} min")
        while True:
            try:
                self.post_update_cycle()
            except Exception as e:
                self.log(f"[error] cycle: {e}\n{traceback.format_exc()}")
            time.sleep(interval * 60)


# ---------------------------------------------------------------- commands
class CommandHandler:
    def __init__(self, engine: Engine):
        self.engine = engine

    def handle(self, chat_id, text):
        text = (text or "").strip()
        if not text.startswith("/"):
            return
        parts = text.split(maxsplit=1)
        cmd = parts[0].split("@")[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""
        try:
            self._dispatch(chat_id, cmd, arg)
        except Exception as e:
            try:
                self.engine.tg.send(chat_id, f"⚠️ Internal error: {esc(e)}")
            except Exception:
                pass
            self.engine.log(f"[error] '{text}': {traceback.format_exc()}")

    def _dispatch(self, chat_id, cmd, arg):
        if cmd in ("/start", "/help"):
            self._help(chat_id)
        elif cmd == "/spotcomp":
            self._spotcomp(chat_id, arg)
        elif cmd in ("/tracks", "/track"):
            self._tracks(chat_id, arg)
        elif cmd in ("/campaigns", "/campaign", "/compaigns", "/compaign"):
            self._campaigns(chat_id, arg)
        elif cmd == "/comps":
            self._comps(chat_id)
        elif cmd == "/watch":
            self._watch(chat_id, arg)
        elif cmd == "/unwatch":
            self._unwatch(chat_id, arg)
        elif cmd == "/now":
            self._now(chat_id)

    def _help(self, chat_id):
        self.engine.tg.send(chat_id,
            "<b>Binance Spot Competition bot</b>\n"
            "🤖 Auto-tracks every running campaign (no setup needed)\n"
            "/spotcomp <i>TOKEN|code</i> — proportional-share estimator card\n"
            "/tracks <i>TOKEN|code</i> [count] — all tracks (Spot/bStock/TradFi/Futures); /tracks 1 = first track\n"
            "/campaigns — all running spot campaigns (with clickable buttons)\n"
            "/comps — all tracked competitions\n"
            "/watch <i>TOKEN|code</i> — force-track a competition\n"
            "/unwatch <i>TOKEN|code</i> — stop tracking one\n"
            "/now — refresh + post now\n"
            "Example: <code>/spotcomp XPL</code>")

    def _spotcomp(self, chat_id, arg):
        if not arg:
            self.engine.tg.send(chat_id, "Usage: /spotcomp <i>TOKEN</i>  (e.g. /spotcomp XPL)")
            return
        self.engine.tg.send(chat_id, f"⏳ Fetching <b>{esc(arg)}</b> …")
        try:
            stats = self.engine.refresh_one(arg)
        except Exception as e:
            self.engine.tg.send(chat_id, f"❌ Error: {esc(e)}")
            return
        if not stats:
            self.engine.tg.send(chat_id,
                                f"❌ No spot competition found for <b>{esc(arg)}</b>.\n"
                                "Try the exact competition code from the Binance URL:\n"
                                "binance.com/en/activity/trading-competition/<code>")
            return
        self.engine.cfg.state["last_track_code"] = arg
        self.engine.cfg.save_state()
        self.engine.tg.send(chat_id, build_card(stats))
        # hint when the campaign has several tracks (Spot/bStock/TradFi/Futures)
        try:
            group, activities = self.engine.api.resolve_competition(arg)
            if group and len(identify_tracks(activities)) > 1:
                self.engine.tg.send(chat_id,
                                    f"ℹ️ This campaign has multiple tracks — "
                                    f"use <code>/tracks {esc(arg)}</code> for all of them.")
        except Exception:
            pass

    def _tracks(self, chat_id, arg):
        # /tracks <code> [count]   → first `count` tracks (default: all)
        # /tracks <count>          → uses the last-used campaign code
        parts = (arg or "").split()
        code = None
        count = None
        for p in parts:
            if p.isdigit():
                count = int(p)
            elif code is None:
                code = p
        if not code:
            code = self.engine.cfg.state.get("last_track_code")
        if not code:
            self.engine.tg.send(chat_id,
                "Usage: /tracks <i>CODE|TOKEN</i> [count]\n"
                "e.g. /tracks 202609tradersleague4 · /tracks 1 (first track)")
            return
        self.engine.cfg.state["last_track_code"] = code
        self.engine.cfg.save_state()
        self.engine.tg.send(chat_id, f"⏳ Fetching tracks for <b>{esc(code)}</b> …")
        try:
            entries = self.engine.refresh_tracks(code)
        except Exception as e:
            self.engine.tg.send(chat_id, f"❌ Error: {esc(e)}")
            return
        if not entries:
            self.engine.tg.send(chat_id,
                                f"❌ No competition found for <b>{esc(code)}</b>.\n"
                                "Try the exact competition code from the Binance URL.")
            return
        if count and count > 0:
            entries = entries[:count]
        self.engine.tg.send(chat_id, build_tracks_message(entries))
        for e in entries:
            if e["kind"] == "single":
                self.engine.tg.send(chat_id, build_card(e["stats"]))
            else:
                self.engine.tg.send(chat_id,
                                    build_multi_card(title_for(e["stats_list"][0]),
                                                     e["stats_list"]))

    def _campaigns(self, chat_id, arg=""):
        if arg:
            self._spotcomp(chat_id, arg)
            return
        self.engine.tg.send(chat_id, "⏳ Fetching running campaigns…")
        try:
            camps = self.engine.get_campaigns(force=False)
        except Exception as e:
            self.engine.tg.send(
                chat_id,
                f"⚠️ Couldn't read the Spot Colosseum page right now.\n"
                f"Binance blocks the reader occasionally — try again in a minute.\n"
                f"<i>({esc(e)})</i>")
            return
        text, keyboard = build_campaigns_message(camps)
        self.engine.tg.send(chat_id, text, reply_markup=keyboard)

    def _comps(self, chat_id):
        items = self.engine.refresh_all()
        if not items:
            self.engine.tg.send(chat_id, "No competitions tracked. Use /watch XPL")
            return
        lines = [build_summary_line(s) for _, s in items]
        self.engine.tg.send(chat_id, "📊 <b>Tracked competitions</b>\n" + "\n".join(lines))

    def _watch(self, chat_id, arg):
        if not arg:
            self.engine.tg.send(chat_id, "Usage: /watch <i>TOKEN|code</i>")
            return
        arg = arg.strip()
        code, status = self.engine._resolve_of(arg)
        if not code:
            self.engine.tg.send(chat_id, f"❌ Can't resolve <b>{esc(arg)}</b> to a spot competition.")
            return
        if status != "PUBLISHED":
            self.engine.tg.send(chat_id, f"🏁 <b>{esc(arg)}</b> has already ended — not watching it.")
            return
        dup = None
        cache = self.engine.cfg.state.get("code_cache") or {}
        for w in list(self.engine.cfg.watchlist):
            if self.engine._norm(w) == self.engine._norm(arg):
                dup = w
                break
            hit = cache.get(self.engine._norm(w))
            wcode = hit.get("code") if hit else None
            if wcode is None:
                wcode = self.engine._code_of(w)
            if wcode and wcode == code:
                dup = w
                break
        if dup:
            self.engine.tg.send(chat_id,
                                f"Already watching <b>{esc(arg)}</b> (as <code>{esc(dup)}</code>).")
            return
        with self.engine.lock:
            if self.engine.watchlist_has(arg):
                self.engine.tg.send(chat_id, f"Already watching <b>{esc(arg)}</b>.")
                return
            self.engine.cfg.watchlist.append(arg)
            excl = {str(k).lower() for k in (self.engine.cfg.state.get("excluded_codes") or [])}
            excl.discard(self.engine._norm(arg))
            if code:
                excl.discard(code)
            self.engine.cfg.state["excluded_codes"] = sorted(excl)
            self.engine.cfg.save_watchlist()
            self.engine.cfg.save_state()
        self.engine.tg.send(chat_id, f"✅ Now watching <b>{esc(arg)}</b>.")

    def _unwatch(self, chat_id, arg):
        if not arg:
            self.engine.tg.send(chat_id, "Usage: /unwatch <i>TOKEN|code</i>")
            return
        arg = arg.strip()
        code = self.engine._code_of(arg)
        resolved = []
        cache = self.engine.cfg.state.get("code_cache") or {}
        for w in list(self.engine.cfg.watchlist):
            hit = cache.get(self.engine._norm(w))
            wcode = hit.get("code") if hit else None
            if wcode is None:
                wcode = self.engine._code_of(w)
            resolved.append((w, wcode))
        with self.engine.lock:
            keep = []
            for w, wcode in resolved:
                wl = self.engine._norm(w)
                if wl == self.engine._norm(arg):
                    continue
                if code and wcode and wcode == code:
                    continue
                keep.append(w)
            removed = len(keep) != len(self.engine.cfg.watchlist)
            if removed:
                self.engine.cfg.watchlist = keep
                excl = {str(k).lower() for k in
                        (self.engine.cfg.state.get("excluded_codes") or [])}
                excl.add(self.engine._norm(arg))
                if code:
                    excl.add(code)
                self.engine.cfg.state["excluded_codes"] = sorted(excl)
                self.engine.cfg.save_watchlist()
                self.engine.cfg.save_state()
        if removed:
            self.engine.tg.send(chat_id, f"🗑 Removed <b>{esc(arg)}</b>.")
        else:
            self.engine.tg.send(chat_id, f"<b>{esc(arg)}</b> is not in the watchlist.")

    def _now(self, chat_id):
        self.engine.tg.send(chat_id, "⏳ Refreshing + posting now…")
        new, cards = self.engine.post_update_cycle(force=True, extra_chat=chat_id)
        self.engine.tg.send(chat_id,
                            f"✅ Done — {len(cards)} card(s) posted, "
                            f"{new} new competition(s) detected.")

    def handle_callback(self, callback_query):
        """Handle inline keyboard button presses."""
        data = callback_query.get("data", "")
        chat_id = callback_query.get("message", {}).get("chat", {}).get("id")
        cb_id = callback_query.get("id")

        if not chat_id or not cb_id:
            return

        if data.startswith("spotcomp:"):
            token = data.split(":", 1)[1].strip()
            self.engine.tg.answer_callback(cb_id, f"Loading {token}…")
            self._spotcomp(chat_id, token)
        else:
            self.engine.tg.answer_callback(cb_id)


# ---------------------------------------------------------------------- main
def main():
    global CONFIG_PATH, WATCHLIST_PATH, STATE_PATH
    ap = argparse.ArgumentParser()
    ap.add_argument("--cli", nargs="?", const="__LIST__",
                    help="run once without Telegram and print card(s)")
    ap.add_argument("--config", default=CONFIG_PATH)
    args = ap.parse_args()

    if args.config != CONFIG_PATH:
        CONFIG_PATH = args.config
        base = os.path.dirname(os.path.abspath(args.config))
        WATCHLIST_PATH = os.path.join(base, "watchlist.json")
        STATE_PATH = os.path.join(base, "state.json")

    cfg = Config()
    set_proxy(cfg.cfg.get("proxy") or os.environ.get("SPOTCOMP_PROXY") or "")
    set_jina_key(cfg.cfg.get("jina_api_key") or os.environ.get("SPOTCOMP_JINA_KEY") or "")
    api = BinanceAPI(proxy=cfg.cfg.get("proxy") or os.environ.get("SPOTCOMP_PROXY") or None,
                     verbose=bool(cfg.cfg.get("binance_verbose")))
    if args.cli:
        run_cli(cfg, api, args.cli)
        return

    if not cfg.cfg.get("bot_token") or "paste-from-BotFather" in cfg.cfg.get("bot_token", ""):
        print("Missing/placeholder bot_token in config.json — see README.md")
        raise SystemExit(1)

    tg = Telegram(cfg.cfg["bot_token"])
    try:
        me = tg.call("getMe")
    except Exception as e:
        print(f"Could not reach Telegram with your bot_token: {e}")
        print("Check that bot_token in config.json is copied from @BotFather.")
        raise SystemExit(1)
    print(f"Bot @{me['username']} started. Watchlist: {cfg.watchlist}")

    engine = Engine(cfg, api, tg)
    handler = CommandHandler(engine)

    thread = threading.Thread(target=engine.loop, daemon=True)
    thread.start()

    offset = 0
    print("Polling updates… (Ctrl+C to stop)")
    while True:
        try:
            updates = tg.get_updates(offset)
        except Exception as e:
            print(f"[warn] getUpdates: {e}")
            time.sleep(5)
            continue
        for u in updates:
            offset = max(offset, u["update_id"] + 1)
            cb = u.get("callback_query")
            if cb:
                handler.handle_callback(cb)
                continue
            msg = u.get("message") or {}
            text = msg.get("text")
            chat_id = msg.get("chat", {}).get("id")
            if not text or not chat_id:
                continue
            handler.handle(chat_id, text)


def run_cli(cfg, api, arg):
    if arg == "__LIST__":
        items = list(cfg.watchlist)
        print("Watchlist:", items)
    else:
        items = [arg] if arg else list(cfg.watchlist)
    for item in items:
        print(f"\n========== {item} ==========")
        try:
            group, activities = api.resolve_competition(item)
        except Exception as e:
            print(f"  (error: {e})")
            continue
        if not group:
            print("  (not found)")
            continue
        stats = compute(api, group, activities)
        if not stats:
            print("  (no activity)")
            continue
        print(build_card(stats))


if __name__ == "__main__":
    main()
