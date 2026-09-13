#!/usr/bin/env python3
"""
Binance Spot Competition → Telegram bot.

Scrapes Binance's public spot-trading-competition endpoints and posts a
"Rank 1001+ proportional share" estimator card for each watched competition,
plus auto-detects new campaigns.

Runs with ONLY the `requests` library. Uses Telegram long-polling (no webhook).

Commands:
  /comp XPL          -> full card for that token / competition code
  /campaigns         -> all running spot campaigns (with clickable buttons)
  /comps             -> one-line status of every watched competition
  /watch XPL         -> start tracking a token or code
  /unwatch XPL       -> stop tracking
  /channels          -> list all broadcast channels
  /addchannel @chan  -> add a broadcast channel
  /removechannel @chan -> remove a broadcast channel
  /now               -> refresh + post cards right now (channel + chat)
  /help
"""

import argparse
import json
import os
import queue as queue_mod
import re
import threading
import time
import traceback

import requests

from binance_api import BinanceAPI
from cards import (build_card, build_campaigns_message, build_multi_card,
                   build_summary_line, build_track_card, build_tracks_message,
                   build_price_card, build_rewards_table_message, compute,
                   compute_all_tracks, esc, extract_reward_date,
                   group_rule_text_for, title_for, volume_fingerprint)
from campaigns import (Campaign, list_running_campaigns, colosseum_entries,
                       enrich, set_proxy, set_jina_key)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
WATCHLIST_PATH = os.path.join(BASE_DIR, "watchlist.json")
STATE_PATH = os.path.join(BASE_DIR, "state.json")

DEFAULT_CONFIG = {
    "bot_token": "",
    "admin_ids": [],
    "channels": [],
    "channel_id": "",
    "refresh_minutes": 15,
    "watchlist": ["PYTH", "RE"],
    "announce_new": True,
    "post_on_update_only": True,
    "auto_remove_ended": True,
    "track_all_running": True,
    "campaigns_cache_minutes": 30,
    "code_aliases": {"tl4": "202609tradersleague4"},
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
        self._save_lock = threading.Lock()

    def save_watchlist(self):
        with self._save_lock:
            save_json(WATCHLIST_PATH, self.watchlist)

    def save_state(self):
        with self._save_lock:
            try:
                snapshot = dict(self.state)
            except Exception:
                snapshot = self.state
            save_json(STATE_PATH, snapshot)

    def save_config(self):
        save_json(CONFIG_PATH, self.cfg)


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

    def is_admin(self, user_id):
        """Check if user_id is in the admin list.
        If admin_ids is empty, returns True (open access).
        """
        raw = self.cfg.cfg.get("admin_ids") or self.cfg.cfg.get("admin_id")
        if not raw:
            return True
        if isinstance(raw, list):
            admins = [str(a).strip() for a in raw if str(a).strip()]
        elif isinstance(raw, (int, str)):
            admins = [str(raw).strip()]
        else:
            admins = []
        if not admins:
            return True
        return str(user_id) in admins

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
        stats = compute(self.api, group, activities, state=self.cfg.state)
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
        entries = compute_all_tracks(self.api, group, activities, state=self.cfg.state)
        with self.lock:
            self.cfg.save_state()
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
                time.sleep(0.1)
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

    def get_channels(self):
        """Return a deduplicated list of channel/chat targets configured in config.json.
        Supports single string/int, list of strings/ints, or comma-separated string,
        under keys 'channels', 'channel_ids', or 'channel_id'.
        """
        raw = (self.cfg.cfg.get("channels")
               or self.cfg.cfg.get("channel_ids")
               or self.cfg.cfg.get("channel_id"))
        if not raw:
            return []
        items = []
        if isinstance(raw, list):
            items = [str(c).strip() for c in raw if str(c).strip()]
        elif isinstance(raw, (int, float)):
            items = [str(int(raw))]
        elif isinstance(raw, str):
            raw = raw.strip()
            if "," in raw:
                items = [c.strip() for c in raw.split(",") if c.strip()]
            elif raw:
                items = [raw]
        # Deduplicate while preserving order
        seen, out = set(), []
        for ch in items:
            chk = ch.lower()
            if chk not in seen:
                seen.add(chk)
                out.append(ch)
        return out

    def add_channel(self, channel):
        ch = str(channel).strip()
        if not ch:
            return False
        current = self.get_channels()
        if any(c.lower() == ch.lower() for c in current):
            return False
        current.append(ch)
        with self.lock:
            self.cfg.cfg["channels"] = current
            # remove legacy single key if present so it doesn't conflict
            self.cfg.cfg.pop("channel_id", None)
            self.cfg.save_config()
        return True

    def remove_channel(self, channel):
        ch = str(channel).strip().lower()
        if not ch:
            return False
        current = self.get_channels()
        new_list = [c for c in current if c.lower() != ch]
        if len(new_list) == len(current):
            return False
        with self.lock:
            self.cfg.cfg["channels"] = new_list
            self.cfg.cfg.pop("channel_id", None)
            self.cfg.save_config()
        return True

    def broadcast(self, text, reply_markup=None):
        """Send a message to all configured channels/chats with pacing."""
        channels = self.get_channels()
        for i, ch in enumerate(channels):
            try:
                self.tg.send(ch, text, reply_markup=reply_markup)
            except Exception as e:
                self.log(f"[warn] broadcast to '{ch}' failed: {e}")
            if i < len(channels) - 1:
                time.sleep(0.05)  # Safe delay between sends for 20-30+ channels

    def post_card(self, stats, chat_id=None, extra_chat=None):
        card = build_card(stats)
        targets, sent = [], set()
        for t in self.get_channels() + [chat_id, extra_chat]:
            if t and str(t) not in sent:
                targets.append(t)
                sent.add(str(t))
        for i, t in enumerate(targets):
            try:
                self.tg.send(t, card)
            except Exception as e:
                self.log(f"[warn] post card to '{t}' failed: {e}")
            if i < len(targets) - 1:
                time.sleep(0.05)
        return card

    def post_update_cycle(self, force=False, extra_chat=None):
        new = self.sync_running_campaigns()
        if new and self.cfg.cfg.get("announce_new"):
            msg = "🆕 New competition(s) detected:\n" + "\n".join(f"• /comp {c}" for c in new)
            self.broadcast(msg)

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
        group = stats.get("group") or {}
        title = ((group.get("i18nContent", {}) or {}).get("homepage", {}) or {}).get("heroBannerContent", {}).get("title") or stats.get("unit") or item
        code = self._norm(group.get("code") or item)

        # Extract reward distribution date & ended date
        ends_ms = stats.get("ends")
        ends_date = time.strftime("%Y-%m-%d", time.gmtime(ends_ms / 1000)) if ends_ms else "—"
        rule_txt = group_rule_text_for(group)
        reward_date = extract_reward_date(rule_txt, ends_ms)
        token_name = stats.get("unit") or title

        # Record in ended history (max 5)
        with self.lock:
            history = list(self.cfg.state.get("ended_competitions_history") or [])
            history = [h for h in history if self._norm(h.get("code")) != code]
            entry = {
                "code": code,
                "token": token_name,
                "ends_date": ends_date,
                "reward_date": reward_date,
                "ts": int(time.time())
            }
            history.insert(0, entry)
            self.cfg.state["ended_competitions_history"] = history[:5]
            self.cfg.save_state()

        if self._remove_from_watchlist(item, code=code or None):
            with self.lock:
                if code:
                    self.cfg.state.pop(f"volfp:{code}", None)
                    self.cfg.state.pop(f"last_post:{code}", None)
                self.cfg.save_state()
            self.log(f"[watch] {item} ended — moved to reward history and removed from watchlist")
            if self.cfg.cfg.get("announce_new"):
                msg = f"🏁 <b>{esc(title)}</b> has ended — removed from watchlist.\n🎁 Reward Distribution: <code>{esc(reward_date)}</code>"
                self.broadcast(msg)

    def get_reward_overview(self):
        """Fetch active campaigns and combine with ended history (max 5) for /reward."""
        active = []
        try:
            camps = self.get_campaigns(force=False)
        except Exception:
            camps = []

        for c in camps:
            code = c.code
            try:
                group = self.api.resource_single(code)
            except Exception:
                group = None
            if group:
                rule_txt = group_rule_text_for(group)
                ends_ms = c.ends_ms or group.get("unpublishedTime")
            else:
                rule_txt = ""
                ends_ms = c.ends_ms

            ends_date = time.strftime("%Y-%m-%d", time.gmtime(ends_ms / 1000)) if ends_ms else "—"
            rw_date = extract_reward_date(rule_txt, ends_ms)
            token_display = c.token
            if "Season" in (c.title or ""):
                m = re.search(r'Season\s+\d+', c.title)
                token_display = m.group(0) if m else c.title
            elif not token_display or token_display == "?" or token_display == "R":
                token_display = c.title or code

            active.append({
                "code": code,
                "token": token_display,
                "ends_date": ends_date,
                "reward_date": rw_date,
            })

        with self.lock:
            ended_history = list(self.cfg.state.get("ended_competitions_history") or [])

        return active, ended_history

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
    ADMIN_COMMANDS = {
        "/addchannel", "/addchan",
        "/removechannel", "/rmchannel", "/delchannel",
        "/channels",
        "/watch", "/unwatch",
        "/now",
    }

    def __init__(self, engine: Engine):
        self.engine = engine

    def handle(self, chat_id, text, user_id=None):
        text = (text or "").strip()
        if not text.startswith("/"):
            return
        parts = text.split(maxsplit=1)
        cmd = parts[0].split("@")[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""
        try:
            self._dispatch(chat_id, cmd, arg, user_id=user_id)
        except Exception as e:
            try:
                self.engine.tg.send(chat_id, f"⚠️ Internal error: {esc(e)}")
            except Exception:
                pass
            self.engine.log(f"[error] '{text}': {traceback.format_exc()}")

    def _dispatch(self, chat_id, cmd, arg, user_id=None):
        if cmd in self.ADMIN_COMMANDS and not self.engine.is_admin(user_id):
            self.engine.tg.send(chat_id, "⛔️ <b>Access Denied:</b> Only the bot admin/owner can use this command.")
            return

        if cmd in ("/start", "/help"):
            self._help(chat_id)
        elif cmd in ("/comp", "/spotcomp"):
            self._comp(chat_id, arg)
        elif cmd in ("/tracks", "/track"):
            self._tracks(chat_id, arg)
        elif cmd in ("/price", "/p"):
            self._price(chat_id, arg)
        elif cmd in ("/reward", "/rewards"):
            self._reward(chat_id)
        elif cmd in ("/campaigns", "/campaign", "/compaigns", "/compaign"):
            self._campaigns(chat_id, arg)
        elif cmd == "/comps":
            self._comps(chat_id)
        elif cmd == "/watch":
            self._watch(chat_id, arg)
        elif cmd == "/unwatch":
            self._unwatch(chat_id, arg)
        elif cmd == "/channels":
            self._channels(chat_id)
        elif cmd in ("/addchannel", "/addchan"):
            self._addchannel(chat_id, arg)
        elif cmd in ("/removechannel", "/rmchannel", "/delchannel"):
            self._removechannel(chat_id, arg)
        elif cmd == "/now":
            self._now(chat_id)

    def _help(self, chat_id):
        self.engine.tg.send(chat_id,
            "<b>Binance Spot Competition bot</b>\n"
            "🤖 Auto-tracks every running campaign (no setup needed)\n"
            "/comp <i>TOKEN|code</i> — proportional-share estimator card\n"
            "/tracks <i>TOKEN|code</i> [n] — all tracks, or 1=Spot 2=bStock 3=TradFi 4=Futures\n"
            "/reward — reward distribution dates table (active & ended)\n"
            "/price <i>TOKEN</i> — live price, 24h high/low & volume\n"
            "/campaigns — all running spot campaigns (with clickable buttons)\n"
            "/comps — all tracked competitions\n"
            "/watch <i>TOKEN|code</i> — force-track a competition\n"
            "/unwatch <i>TOKEN|code</i> — stop tracking one\n"
            "/channels — list all broadcast channels\n"
            "/addchannel <i>@chan|ID</i> — add a broadcast channel\n"
            "/removechannel <i>@chan|ID</i> — remove a broadcast channel\n"
            "/now — refresh + post now\n"
            "Example: <code>/comp XPL</code> · <code>/reward</code> · <code>/price BTC</code>")

    def _reward(self, chat_id):
        self.engine.tg.send(chat_id, "⏳ Fetching reward distribution dates…")
        try:
            active, ended = self.engine.get_reward_overview()
            msg = build_rewards_table_message(active, ended)
            self.engine.tg.send(chat_id, msg)
        except Exception as e:
            self.engine.tg.send(chat_id, f"❌ Error: {esc(e)}")

    def _price(self, chat_id, arg):
        if not arg:
            self.engine.tg.send(chat_id, "Usage: /price <i>TOKEN</i>  (e.g. <code>/price btc</code>, <code>/price eth</code>, <code>/price sol/usdt</code>)")
            return
        sym = arg.strip()
        try:
            data = self.engine.api.ticker_24hr(sym)
        except Exception as e:
            self.engine.tg.send(chat_id, f"❌ Error fetching price: {esc(e)}")
            return
        if not data:
            self.engine.tg.send(chat_id, f"❌ No market data found on Binance for <b>{esc(sym.upper())}</b>.\nTry a valid pair like <code>/price btc</code> or <code>/price ethusdt</code>.")
            return
        self.engine.tg.send(chat_id, build_price_card(data))

    def _comp(self, chat_id, arg):
        if not arg:
            self.engine.tg.send(chat_id, "Usage: /comp <i>TOKEN</i>  (e.g. /comp XPL)")
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
        with self.engine.lock:
            self.engine.cfg.state["last_track_code"] = arg
            self.engine.cfg.save_state()
        self.engine.tg.send(chat_id, build_card(stats))

    def _tracks(self, chat_id, arg):
        # /tracks             → summary + every track card (last-used competition)
        # /tracks <code>      → summary + every track card of <code>
        # /tracks <code> <n>  → ONLY track #n (1=Spot, 2=bStock, 3=TradFi, 4=Futures)
        # /tracks <n>         → ONLY track #n of the last-used competition
        parts = (arg or "").split()
        code = None
        n = None
        for p in parts:
            if p.isdigit():
                n = int(p)
            elif code is None:
                code = p
        if not code:
            code = self.engine.cfg.state.get("last_track_code")
        if not code:
            self.engine.tg.send(chat_id,
                "Usage: /tracks <i>CODE</i> [<i>n</i>]\n"
                "e.g. /tracks tl4 (all) · /tracks 1 (Spot) · /tracks tl4 3 (TradFi)")
            return
        with self.engine.lock:
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

        # single-track request → show just that one card
        if n is not None and n >= 1:
            if n > len(entries):
                self.engine.tg.send(chat_id,
                                    f"❌ <b>{esc(code)}</b> has only {len(entries)} tracks "
                                    f"(1..{len(entries)}). You asked for #{n}.")
                return
            e = entries[n - 1]
            if e["kind"] == "single":
                self.engine.tg.send(chat_id, build_track_card(e["stats"]))
            else:
                self.engine.tg.send(chat_id,
                                    build_multi_card(title_for(e["stats_list"][0]),
                                                     e["stats_list"]))
            return

        # full overview
        self.engine.tg.send(chat_id, build_tracks_message(entries))
        for e in entries:
            if e["kind"] == "single":
                self.engine.tg.send(chat_id, build_track_card(e["stats"]))
            else:
                self.engine.tg.send(chat_id,
                                    build_multi_card(title_for(e["stats_list"][0]),
                                                     e["stats_list"]))

    def _campaigns(self, chat_id, arg=""):
        if arg:
            self._comp(chat_id, arg)
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

    def _channels(self, chat_id):
        channels = self.engine.get_channels()
        if not channels:
            self.engine.tg.send(chat_id, "No broadcast channels configured.\nUse <code>/addchannel @your_channel</code> or <code>/addchannel -100xxxxxxxxxx</code>")
            return
        lines = [f"📢 <b>Broadcast Channels ({len(channels)}):</b>", ""]
        for i, ch in enumerate(channels, 1):
            lines.append(f"{i}. <code>{esc(ch)}</code>")
        lines.append("")
        lines.append("<i>Use /addchannel to add more or /removechannel to remove.</i>")
        self.engine.tg.send(chat_id, "\n".join(lines))

    def _addchannel(self, chat_id, arg):
        if not arg:
            self.engine.tg.send(chat_id, "Usage: /addchannel <i>@channel_username</i> or <i>-100xxxxxxxxxx</i>")
            return
        ch = arg.strip()
        ok = self.engine.add_channel(ch)
        if ok:
            total = len(self.engine.get_channels())
            self.engine.tg.send(chat_id, f"✅ Added <code>{esc(ch)}</code> to broadcast list (Total: {total}).")
        else:
            self.engine.tg.send(chat_id, f"⚠️ Channel <code>{esc(ch)}</code> is already in the list or invalid.")

    def _removechannel(self, chat_id, arg):
        if not arg:
            self.engine.tg.send(chat_id, "Usage: /removechannel <i>@channel_username</i> or <i>-100xxxxxxxxxx</i>")
            return
        ch = arg.strip()
        ok = self.engine.remove_channel(ch)
        if ok:
            total = len(self.engine.get_channels())
            self.engine.tg.send(chat_id, f"🗑 Removed <code>{esc(ch)}</code> from broadcast list (Total: {total}).")
        else:
            self.engine.tg.send(chat_id, f"⚠️ Channel <code>{esc(ch)}</code> was not found in the broadcast list.")

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

        if data.startswith("comp:") or data.startswith("spotcomp:"):
            token = data.split(":", 1)[1].strip()
            self.engine.tg.answer_callback(cb_id, f"Loading {token}…")
            self._comp(chat_id, token)
        else:
            self.engine.tg.answer_callback(cb_id)


# ---------------------------------------------------------------------- main
def main():
    global CONFIG_PATH, WATCHLIST_PATH, STATE_PATH
    ap = argparse.ArgumentParser()
    ap.add_argument("--cli", nargs="?", const="__LIST__",
                    help="run once without Telegram and print card(s)")
    ap.add_argument("--price", help="check live 24h ticker price for a token (e.g. --price btc)")
    ap.add_argument("--reward", action="store_true", help="show reward distribution dates table")
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
    api.set_aliases(cfg.cfg.get("code_aliases") or {})
    if args.price:
        d = api.ticker_24hr(args.price)
        if not d:
            print(f"Token '{args.price}' not found on Binance.")
        else:
            print(build_price_card(d))
        return

    if args.reward:
        engine = Engine(cfg, api, None)
        active, ended = engine.get_reward_overview()
        print(build_rewards_table_message(active, ended))
        return

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

    # Non-blocking command handling: the main loop ONLY polls Telegram and
    # enqueues commands; a worker thread executes them. This keeps the bot
    # responsive even while a slow command (e.g. /tracks) is fetching data.
    command_q = queue_mod.Queue(maxsize=500)

    def _command_worker():
        while True:
            try:
                kind, a, b, c = command_q.get()
                if kind == "msg":
                    handler.handle(a, b, user_id=c)
                elif kind == "cb":
                    handler.handle_callback(a)
            except Exception:
                try:
                    engine.log(f"[worker] {traceback.format_exc()}")
                except Exception:
                    pass
            finally:
                command_q.task_done()

    # small pool so a few commands run in parallel (3 workers ≈ 3 commands at once)
    for _ in range(3):
        threading.Thread(target=_command_worker, daemon=True).start()

    offset = 0
    reload_flag = os.path.join(BASE_DIR, ".reload")
    print("Polling updates… (Ctrl+C to stop)")
    while True:
        # self-restart: touch ~/spot-comp/.reload to load newly uploaded code
        if os.path.exists(reload_flag):
            try:
                os.remove(reload_flag)
            except Exception:
                pass
            print("[reload] flag detected — exiting so the supervisor restarts me")
            break
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
                command_q.put(("cb", cb, None, None))
                continue
            msg = u.get("message") or {}
            text = msg.get("text")
            chat_id = msg.get("chat", {}).get("id")
            user_id = (msg.get("from") or {}).get("id")
            if not text or not chat_id:
                continue
            # instant typing indicator so the bot feels alive immediately
            try:
                tg.call("sendChatAction", chat_id=chat_id, action="typing")
            except Exception:
                pass
            command_q.put(("msg", chat_id, text, user_id))


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

