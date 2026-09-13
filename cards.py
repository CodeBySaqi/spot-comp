"""
Card computation + Telegram formatting for the spot-competition estimator.

Replicates the "Rank 1001+ proportional share" card:

    📐 XPL Trading Tournament
    🧮 Rule: (your volume ÷ tail volume) × 800,000 XPL, max 500.0000 XPL
    👥 Tail (rank 1001+): N users · $V total volume
    📈 Rate: R XPL (~$x) per $1,000 volume
    🕒 Leaderboard updated: YYYY-MM-DD HH:MM UTC
    🎁 Volume → reward (× vs old equal split)
"""

import datetime
import html as _html
import json
import math
import re
import time

from binance_api import (group_rule_text, is_i18n_key, load_i18n,
                         rich_text_to_text, tail_cap_from_text)

TOP1000_CUTOFF = 1000


def esc(s):
    """Escape a string for Telegram HTML parse mode."""
    return _html.escape(str(s), quote=False)


def fmt_usd(v):
    return f"${v:,.2f}"


def fmt_num(v, dp=4):
    return f"{v:,.{dp}f}".rstrip("0").rstrip(".") if isinstance(v, float) else f"{v:,}"


def fmt_fixed(v, dp=4):
    """Format keeping exactly `dp` decimals (e.g. 500.0000)."""
    return f"{float(v):,.{dp}f}"


def pick_main_activity(activities):
    """Choose the MAIN reward pool activity (has the 1001+ proportional tail)."""
    mains = [a for a in activities if "main" in (a.get("i18nContent", {}).get("title") or "").lower()]
    if mains:
        return mains[0]
    # otherwise: activity whose last prize tier starts at >= 200 and ends at None
    for a in activities:
        pl = (a.get("globalContent", {}).get("rankingSetting", {}) or {}).get("rankingPrizeList") or []
        if pl and pl[-1].get("end") is None and (pl[-1].get("start") or 0) >= 200:
            return a
    return activities[0] if activities else None


def get_tail_tier(activity):
    pl = (activity.get("globalContent", {}).get("rankingSetting", {}) or {}).get("rankingPrizeList") or []
    for t in pl:
        if t.get("end") is None and (t.get("start") or 0) >= 200:
            return t
    # no proportional tail in this activity (e.g. fixed tiers only) — not an error
    return None


def get_tier_for_rank(pl, rank):
    """Find the prize tier that covers a given rank (1-based)."""
    for t in pl:
        start = t.get("start") or 1
        end = t.get("end")
        if end is None:
            return t
        if start <= rank <= end:
            return t
    return None


def compute(api, group, activities, state=None):
    """Gather all live stats for the MAIN activity and compute the estimator."""
    act = pick_main_activity(activities)
    if act is None:
        return None

    gc = act.get("globalContent", {}) or {}
    rs = gc.get("rankingSetting", {}) or {}
    rp = gc.get("rewardPoolSetting", {}) or {}
    unit = (rp.get("unit") or "TOKEN").upper()
    pl = rs.get("rankingPrizeList") or []
    tail_tier = get_tail_tier(act)
    top1000_tier = get_tier_for_rank(pl, TOP1000_CUTOFF)
    # If the tier covering rank 1000 is itself the open-ended tail, there is
    # no separate "top 1000" tier (rare structure) — treat it as none.
    if top1000_tier and top1000_tier.get("end") is None:
        top1000_tier = None

    tail_pool = tail_tier.get("fixedAmount") if tail_tier else None
    top1000_pool = top1000_tier.get("fixedAmount") if top1000_tier else None
    if top1000_tier:
        top1000_span = ((top1000_tier.get("end") or TOP1000_CUTOFF)
                        - (top1000_tier.get("start") or 1) + 1)
    else:
        top1000_span = 1
    top1000_per_user = (top1000_pool / top1000_span) if top1000_pool else None

    # leaderboard pages 1..10 (100 rows each) to cover ranks 1..1000
    rows = []
    eligible_users = None
    eligible_vol = None
    updated = None
    for page in range(1, 11):
        lb = api.leaderboard_page(act["id"], page_index=page, page_size=100)
        if not lb:
            break
        eligible_users = lb.get("eligibleUserCount")
        eligible_vol = lb.get("eligibleTradingVolume")
        updated = lb.get("updatedTime")
        batch = ((lb.get("resourceSummaryList") or {}).get("data")) or []
        rows.extend(batch)
        total = (lb.get("resourceSummaryList") or {}).get("total") or 0
        if page * 100 >= total:
            break
        time.sleep(0.05)

    sum_top1000 = sum((r.get("tradingVolume") or r.get("grade") or 0)
                      for r in rows
                      if (r.get("sequence") or 10**9) <= TOP1000_CUTOFF)
    rank1000_row = next((r for r in rows if (r.get("sequence") or 0) == TOP1000_CUTOFF), None)
    rank1_row = next((r for r in rows if (r.get("sequence") or 0) == 1), None)

    tail_users = max(0, (eligible_users or 0) - TOP1000_CUTOFF)
    tail_vol = max(0.0, (eligible_vol or 0) - sum_top1000)

    price = api.token_price(unit)

    # --- CAP DETECTION ---
    # Only use cap if explicitly found in rules text (incl. Binance i18n
    # resources for multi-track campaigns like Traders League 4).
    cap, cap_unit = _extract_cap(group, act, unit)
    cap_unit = cap_unit or unit

    rate_per_1000 = (tail_pool / tail_vol * 1000) if (tail_pool and tail_vol) else 0
    equal_split = (tail_pool / tail_users) if (tail_pool and tail_users) else 0

    return {
        "group": group,
        "activity": act,
        "activities": activities,
        "unit": unit,
        "price": price,
        "pool": (rp.get("rewardAmountList") or [{}])[0].get("amount"),
        "tail_pool": tail_pool,
        "cap": cap,
        "cap_unit": cap_unit,
        "top1000_per_user": top1000_per_user,
        "eligible_users": eligible_users,
        "eligible_vol": eligible_vol,
        "tail_users": tail_users,
        "tail_vol": tail_vol,
        "rank1000_vol": (rank1000_row.get("tradingVolume") or rank1000_row.get("grade")) if rank1000_row else None,
        "rank1_vol": (rank1_row.get("tradingVolume") or rank1_row.get("grade")) if rank1_row else None,
        "top_rows": [r for r in rows if (r.get("sequence") or 0) <= 5][:5],
        "updated": updated,
        "ends": act.get("unpublishedTime") or act.get("taskExpiredTime"),
        "status": group.get("status"),
        "ended": group.get("status") == "UNPUBLISHED",
        "rate_per_1000": rate_per_1000,
        "equal_split": equal_split,
        "qualify": gc.get("leaderboardQualifyThresholds"),
        "pairs": gc.get("includeSpotTradingPairList") or gc.get("includeTradingPairList") or [],
    }


def group_rule_text_for(group):
    return group_rule_text(group)


def token_from_code(code):
    """Extract a token symbol from a wave-style code (e.g. ...wave-REZ-R1 → REZ)."""
    m = re.search(r"wave-([A-Za-z0-9]+?)(?:-?[Rr]?\d+)?$", code or "")
    if m:
        tok = m.group(1).upper()
        if len(tok) >= 2 and not tok.isdigit():
            return tok
    return None


_GENERIC_WORDS = {
    "spot", "altcoin", "festival", "wave", "waves", "trading",
    "competition", "tournament", "round", "the", "season", "carnival",
}
_COMPOUND_WORDS = {
    "tradersleague": "Traders League",
}


def humanize_code(code):
    """Turn a competition code into a readable fallback title.

    e.g. "202609tradersleague4" → "Traders League 4"
         "spot-trading-festival-wave-r3" → "Round 3"
    """
    code = (code or "").strip()
    if not code:
        return None
    words = []
    for part in re.split(r"[-/_]+", code):
        part = re.sub(r"^\d{4,}", "", part)
        m = re.match(r"^(.*?[a-zA-Z])(\d+)$", part)
        base = m.group(1) if m else part
        num = m.group(2) if m else None
        low = base.lower()
        if low == "r" and num:
            words.append(f"Round {num}")
            continue
        if low in _GENERIC_WORDS:
            continue
        if not base:
            continue
        pretty = _COMPOUND_WORDS.get(low, base[:1].upper() + base[1:])
        words.append(pretty)
        if num:
            words.append(num)
    return " ".join(words).strip() or None


def title_for(stats):
    group = stats["group"]
    i18n = group.get("i18nContent", {}) or {}
    hp = i18n.get("homepage", {}) or {}
    hero = hp.get("heroBannerContent", {}) or {}
    seo = hp.get("seoContent", {}) or {}
    # 1) real title from Binance (not an untranslated i18n key)
    for src in (hero, seo, hp):
        t = str(src.get("title") or "").strip()
        if t and t.lower() != "null" and not is_i18n_key(t):
            return t
    # 2) token embedded in the code (e.g. ...wave-REZ-R1)
    code = group.get("code") or ""
    tok = token_from_code(code)
    if tok:
        return f"{tok} Trading Competition"
    # 3) humanize the code itself (e.g. 202609tradersleague4)
    human = humanize_code(code)
    if human:
        return human
    # 4) last resort
    return f"{stats['unit']} Trading Competition"


def _fmt_ts(ms):
    if not ms:
        return "—"
    return time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(ms / 1000))


def build_card(stats):
    """Build the Telegram (HTML) card."""
    L = []
    unit = stats["unit"]
    price = stats["price"]
    tail_pool = stats["tail_pool"]

    L.append(f"📐 <b>{esc(title_for(stats))}</b>")
    pairs = " · ".join(stats["pairs"]) if stats["pairs"] else ""
    main_pool = None
    for a in stats["activities"]:
        if a.get("id") == stats["activity"]["id"]:
            al = (a.get("globalContent", {}).get("rewardPoolSetting", {}) or {}).get("rewardAmountList") or []
            if al:
                main_pool = al[0].get("amount")
    if main_pool is not None and tail_pool is not None:
        L.append(f"Main pool {esc(fmt_num(main_pool,0))} {unit} · tail pool {esc(fmt_num(tail_pool,0))} {unit}")
    if pairs:
        L.append(f"Pairs: <code>{esc(pairs)}</code>")

    # --- top ranks ---
    rows = stats["top_rows"]
    if rows:
        L.append("")
        L.append("🏆 <b>Top ranks</b>")
        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
        lines = []
        for r in rows:
            seq = r.get("sequence") or 0
            name = (r.get("nickName") or "—")
            vol = r.get("tradingVolume") or r.get("grade") or 0
            medal = medals.get(seq, f"#{seq}")
            lines.append(f"{medal} {esc(name)} — <code>{fmt_usd(vol)}</code>")
        L.extend(lines)
        if stats["rank1000_vol"] is not None:
            L.append(f"🎯 #1000 (cutoff) — <code>{fmt_usd(stats['rank1000_vol'])}</code>")

    # --- totals ---
    L.append("")
    if stats["eligible_users"] is not None:
        L.append(f"👥 <b>All eligible:</b> {stats['eligible_users']:,} users · "
                 f"<code>{fmt_usd(stats['eligible_vol'] or 0)}</code> total volume")

    # --- tail ---
    L.append("")
    L.append(f"📉 <b>Tail (rank 1001+):</b> {stats['tail_users']:,} users · "
             f"<code>{fmt_usd(stats['tail_vol'])}</code> total volume")

    # --- rate / rule / examples ---
    if tail_pool is not None:
        rate = stats["rate_per_1000"]
        if rate:
            usd = f" (~{fmt_usd(rate * (price or 0))})" if price else ""
            L.append(f"📈 <b>Rate:</b> <code>{fmt_fixed(rate)} {unit}</code>{esc(usd)} per $1,000 volume")

        # Only show "max X" if a real cap was found in the rules
        if stats["cap"]:
            cap_txt = f", max <code>{fmt_fixed(stats['cap'], 4)} {esc(stats['cap_unit'] or unit)}</code>"
        else:
            cap_txt = ""
        L.append(f"🧮 <b>Rule:</b> (your volume ÷ tail volume) × "
                 f"<code>{fmt_num(tail_pool, 0)} {unit}</code>{cap_txt}")

        ex_vols = stats.get("example_volumes") or (60000, 30000, 10000, 5000, 1000)
        if stats["equal_split"]:
            L.append("")
            L.append("🎁 <b>Volume → reward</b>")
            for v in ex_vols:
                if stats["tail_vol"]:
                    raw_rw = v / stats["tail_vol"] * tail_pool
                    rw = min(raw_rw, stats["cap"]) if stats["cap"] else raw_rw
                else:
                    rw = 0
                    raw_rw = 0
                mult = rw / stats["equal_split"] if stats["equal_split"] else 0
                capped = " · CAPPED" if stats["cap"] and rw >= stats["cap"] - 1e-9 else ""
                usd = f" (~{fmt_usd(rw * (price or 0))})" if price else ""
                L.append(f"<code>${v:,} → {fmt_fixed(rw, 4)} {unit}{esc(usd)} · {mult:.2f}×{capped}</code>")
    else:
        L.append("ℹ️ <i>No proportional tail tier for this competition.</i>")

    if stats["top1000_per_user"] is not None:
        usd = f" (~{fmt_usd(stats['top1000_per_user'] * (price or 0))})" if price else ""
        L.append(f"ℹ️ Top-1000 tier pays <code>{fmt_fixed(stats['top1000_per_user'], 4)} {unit}</code>{esc(usd)} "
                 f"each — a different tier, not this one.")

    if stats.get("ended"):
        L.append("🏁 <i>This competition has ended — showing the final leaderboard.</i>")
    else:
        L.append("⚠️ <i>Live estimate — tail volume keeps growing, so your share shrinks unless you keep trading.</i>")

    L.append("")
    L.append(f"🕒 Updated: {esc(_fmt_ts(stats['updated']))} · ⏳ Ends: {esc(_fmt_ts(stats['ends']))}")
    code = stats["group"].get("code") or ""
    if code:
        L.append(f"🔗 binance.com/en/activity/trading-competition/{esc(code)}")

    return "\n".join(L)


def build_summary_line(stats):
    """One-line summary used by /comps."""
    unit = stats["unit"]
    rate = stats["rate_per_1000"]
    tail = f"{stats['tail_users']:,}u · {fmt_usd(stats['tail_vol'])}"
    rate_txt = f"{fmt_num(rate)} {unit}/$1k" if rate else "—"
    ends = _fmt_ts(stats["ends"])
    state = "🏁 ended" if stats.get("ended") else f"ends {ends}"
    return (f"<b>{esc(title_for(stats))}</b> — tail {tail} · {rate_txt} · {state}")


def volume_fingerprint(stats, dp=2):
    """A signature of the leaderboard's VOLUME metrics only."""
    def v(x):
        try:
            return f"{float(x):.{dp}f}"
        except (TypeError, ValueError):
            return "-"

    top = []
    for r in (stats.get("top_rows") or [])[:5]:
        seq = r.get("sequence") or 0
        vol = r.get("tradingVolume") or r.get("grade") or 0
        top.append(f"{seq}:{v(vol)}")

    r1 = stats.get("rank1_vol")
    r1000 = stats.get("rank1000_vol")
    parts = [
        f"u:{int(stats.get('eligible_users') or 0)}",
        f"v:{v(stats.get('eligible_vol'))}",
        f"tu:{int(stats.get('tail_users') or 0)}",
        f"tv:{v(stats.get('tail_vol'))}",
        f"r1:{v(r1) if r1 is not None else '-'}",
        f"r1000:{v(r1000) if r1000 is not None else '-'}",
        "top:" + ",".join(top),
    ]
    return "|".join(parts)


def build_campaigns_message(campaigns):
    """Telegram message + inline keyboard for running spot campaigns.

    Returns (text, reply_markup_json_string).
    reply_markup is None if no campaigns.
    """
    if not campaigns:
        return "No running spot campaigns found right now.", None

    lines = [f"🏟 <b>Running Spot Campaigns</b> ({len(campaigns)})", ""]
    medals = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]

    keyboard_buttons = []

    for i, c in enumerate(campaigns):
        num = medals[i] if i < len(medals) else f"{i + 1}."
        title = c.title or (f"{c.token} Trading Tournament" if c.token and c.token != "?" else c.code)

        lines.append(f"{num} <b>{esc(title)}</b>")

        bits = []
        if c.prize:
            bits.append(f"🎁 {esc(c.prize)}")
        if c.ends_ms:
            bits.append(f"⏳ ends {esc(_fmt_ts(c.ends_ms))}")
        if bits:
            lines.append("   " + " · ".join(bits))

        # Use the competition code for callback (always correct)
        display = c.token if c.token and c.token != "?" else c.code
        lines.append("")

        # Button uses full code so /comp resolves correctly
        keyboard_buttons.append([{
            "text": f"📊 {display}",
            "callback_data": f"comp:{c.code}"
        }])

    reply_markup = json.dumps({
        "inline_keyboard": keyboard_buttons
    })

    lines.append("<i>👆 Tap a button below to see the full card</i>")

    return "\n".join(lines).rstrip(), reply_markup


def fmt_price_val(v, is_usd=True):
    val = float(v)
    is_neg = val < 0
    val_abs = abs(val)
    prefix = "$" if is_usd else ""
    if val_abs >= 1000:
        formatted = f"{prefix}{val_abs:,.2f}"
    elif val_abs >= 1:
        formatted = f"{prefix}{val_abs:,.4f}".rstrip("0").rstrip(".")
    elif val_abs >= 0.0001:
        formatted = f"{prefix}{val_abs:,.6f}".rstrip("0").rstrip(".")
    else:
        formatted = f"{prefix}{val_abs:,.8f}".rstrip("0").rstrip(".")
    return f"-{formatted}" if is_neg else formatted


def build_price_card(t):
    """Build a 24-hour ticker price card."""
    sym = t.get("symbol", "")
    quotes = ["USDT", "USDC", "FDUSD", "BTC", "BNB", "EUR", "TRY"]
    base, quote = sym, ""
    for q in quotes:
        if sym.endswith(q) and len(sym) > len(q):
            base = sym[:-len(q)]
            quote = q
            break

    pair_display = f"{base}/{quote}" if quote else sym
    is_usd_quote = quote in ("USDT", "USDC", "FDUSD", "USD")

    last_price = float(t.get("lastPrice", 0))
    high_price = float(t.get("highPrice", 0))
    low_price = float(t.get("lowPrice", 0))
    price_change = float(t.get("priceChange", 0))
    price_change_pct = float(t.get("priceChangePercent", 0))
    vol_base = float(t.get("volume", 0))
    vol_quote = float(t.get("quoteVolume", 0))

    trend_emoji = "🟢" if price_change_pct >= 0 else "🔴"
    change_sign = "+" if price_change >= 0 else ""
    chg_val_str = fmt_price_val(price_change, is_usd_quote)
    if price_change >= 0:
        chg_val_str = f"+{chg_val_str}"

    time_str = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
    trade_link = f"https://www.binance.com/en/trade/{base}_{quote}" if quote else f"https://www.binance.com/en/trade/{sym}"

    lines = [
        f"🪙 <b>{esc(pair_display)} Live Price</b>",
        "",
        f"💵 <b>Price:</b> <code>{fmt_price_val(last_price, is_usd_quote)}</code>",
        f"📊 <b>24h Change:</b> {trend_emoji} <code>{change_sign}{price_change_pct:.2f}% ({chg_val_str})</code>",
        "",
        f"📈 <b>24h High:</b> <code>{fmt_price_val(high_price, is_usd_quote)}</code>",
        f"📉 <b>24h Low:</b> <code>{fmt_price_val(low_price, is_usd_quote)}</code>",
        f"💰 <b>24h Volume:</b> <code>{fmt_price_val(vol_quote, is_usd_quote)}</code> ({vol_base:,.2f} {base})",
        "",
        f"🕒 <i>{time_str}</i>",
        f"🔗 <a href=\"{trade_link}\">Trade {esc(pair_display)} on Binance</a>",
    ]
    return "\n".join(lines)


def extract_reward_date(rule_text, ends_ms=None):
    """Extract reward distribution date from Binance competition rules text.
    Handles exact dates (e.g. 'by 2026-09-17') and relative offsets ('within X days').
    """
    if not rule_text:
        return "TBA"

    # Pattern 1: Exact date 'distributed ... by YYYY-MM-DD'
    m1 = re.search(r'distribut\w*\s+.*?by\s*(\d{4}[-/]\d{2}[-/]\d{2})', rule_text, re.IGNORECASE)
    if m1:
        return m1.group(1).replace('/', '-')

    # Pattern 2: 'distributed within X days/weeks'
    m2 = re.search(r'distribut\w*\s+within\s+(\d+)\s*(working\s+|business\s+)?(day|week)s?', rule_text, re.IGNORECASE)
    if m2 and ends_ms:
        num = int(m2.group(1))
        unit = m2.group(3).lower()
        days = num * 7 if unit == 'week' else num
        try:
            end_dt = datetime.datetime.fromtimestamp(ends_ms / 1000, tz=datetime.timezone.utc)
            dist_dt = end_dt + datetime.timedelta(days=days)
            return dist_dt.strftime('%Y-%m-%d')
        except Exception:
            return f"within {num} {unit}s"

    # Pattern 3: General YYYY-MM-DD near distribution keywords
    m3 = re.search(r'(?:reward\s+distribution|distribution\s+date).*?(\d{4}[-/]\d{2}[-/]\d{2})', rule_text, re.IGNORECASE)
    if m3:
        return m3.group(1).replace('/', '-')

    # Pattern 4: Fallback ~14 days after competition end
    if ends_ms:
        try:
            end_dt = datetime.datetime.fromtimestamp(ends_ms / 1000, tz=datetime.timezone.utc)
            dist_dt = end_dt + datetime.timedelta(days=14)
            return dist_dt.strftime('%Y-%m-%d')
        except Exception:
            pass

    return "TBA"


def format_ascii_table(headers, rows):
    """Format headers and rows into a clean ASCII table."""
    if not rows:
        return ""
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, val in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(val)))

    col_widths = [w + 1 for w in col_widths]

    top = "┌" + "┬".join("─" * (w + 1) for w in col_widths) + "┐"
    mid = "├" + "┼".join("─" * (w + 1) for w in col_widths) + "┤"
    bot = "└" + "┴".join("─" * (w + 1) for w in col_widths) + "┘"

    header_str = "│" + "│".join(f" {headers[i]:<{col_widths[i]}}" for i in range(len(headers))) + "│"

    row_strs = []
    for r in rows:
        r_str = "│" + "│".join(f" {str(r[i]):<{col_widths[i]}}" for i in range(len(r))) + "│"
        row_strs.append(r_str)

    return "\n".join([top, header_str, mid] + row_strs + [bot])


def build_rewards_table_message(active_campaigns, ended_history):
    """Build the /reward message with tables for active and ended campaigns."""
    lines = ["🎁 <b>Binance Spot Competitions — Reward Dates</b>", ""]

    # Active Section
    lines.append("🟢 <b>Active Campaigns</b>")
    if active_campaigns:
        active_rows = []
        for c in active_campaigns:
            name = c.get("name") or c.get("token") or c.get("code") or "—"
            ends = c.get("ends_date") or "—"
            rw_date = c.get("reward_date") or "TBA"
            active_rows.append([name, ends, rw_date])
        table_str = format_ascii_table(["Competition", "Ends", "Reward Date"], active_rows)
        lines.append(f"<pre>{esc(table_str)}</pre>")
    else:
        lines.append("<i>No active campaigns running right now.</i>")

    lines.append("")

    # Ended Section (Max 10)
    lines.append("🏁 <b>Recently Ended</b>")
    if ended_history:
        ended_rows = []
        for c in ended_history[:10]:
            name = c.get("name") or c.get("token") or c.get("code") or "—"
            ends = c.get("ends_date") or c.get("ended") or "—"
            rw_date = c.get("reward_date") or "TBA"
            ended_rows.append([name, ends, rw_date])
        table_str = format_ascii_table(["Competition", "Ended", "Reward Date"], ended_rows)
        lines.append(f"<pre>{esc(table_str)}</pre>")
    else:
        lines.append("<i>No ended competitions recorded yet.</i>")

    lines.append("")
    lines.append("ℹ️ <i>Rewards are distributed as token vouchers to your Binance Rewards Hub.</i>")
    return "\n".join(lines)




def metric_label(act):
    """Ranking metric label for a track (volume / AUM / eligible volume)."""
    t = (((act.get("i18nContent") or {}).get("title")) or "").lower()
    if "bstock" in t or "aum" in t:
        return "AUM"
    if "futures" in t:
        return "eligible volume"
    return "volume"


def _tier_shape(pl):
    """Classify a prize-tier list → (shape, tail_start, pool, top_n).

    - "tail" : open-ended last tier (rank N+ proportional share)
    - "topN" : a single fixed tier 1..N (top-N proportional split)
    - "fixed": fixed tiers only (sprints / side tasks)
    """
    tail = next((t for t in pl if t.get("end") is None), None)
    if tail:
        return "tail", tail.get("start"), tail.get("fixedAmount"), None
    if len(pl) == 1:
        t = pl[0]
        return "topN", None, t.get("fixedAmount"), t.get("end")
    return "fixed", None, None, None


def resolve_title_key(key, i18n):
    """Resolve an i18n key to text; clean up known title junk."""
    t = (i18n or {}).get(key, key)
    t = re.sub(r"\s*-\s*", " — ", t)   # "Futures Competition- Round 1"
    return t


def identify_tracks(activities):
    """Return the main competition activities (exclude sprints & side tasks)."""
    tracks = []
    for a in activities:
        if a.get("status") != "PUBLISHED":
            continue
        gc = a.get("globalContent", {}) or {}
        rs = gc.get("rankingSetting", {}) or {}
        pl = rs.get("rankingPrizeList") or []
        if not pl:
            continue
        rp = gc.get("rewardPoolSetting", {}) or {}
        pool = (rp.get("rewardAmountList") or [{}])[0].get("amount") or 0
        title = ((a.get("i18nContent") or {}).get("title") or "").lower()
        if "sprint" in title:
            continue
        if "leaderboard" in title:
            continue
        if pool and pool <= 1:
            continue
        shape, _, _, _ = _tier_shape(pl)
        if shape in ("tail", "topN"):
            tracks.append(a)
    return tracks


def pick_primary_track(activities):
    """Pick the single best track for /spotcomp (prefer spot, then any tail)."""
    tracks = identify_tracks(activities)
    if not tracks:
        return None
    for a in tracks:
        title = ((a.get("i18nContent") or {}).get("title") or "").lower()
        if "spot" in title:
            return a
    for a in tracks:
        shape, _, _, _ = _tier_shape(
            (a.get("globalContent", {}).get("rankingSetting", {}) or {}).get("rankingPrizeList") or [])
        if shape == "tail":
            return a
    return tracks[0]


def _metric_of(r):
    """A leaderboard row's ranking metric (grade: AUM / eligible volume / volume)."""
    g = r.get("grade")
    if g is not None:
        return float(g)
    return float(r.get("tradingVolume") or 0)


def _pairs_of(act):
    gc = act.get("globalContent", {}) or {}
    for key in ("includeSpotTradingPairList", "includeTradingPairList",
                "includeFuturesUmTradingPairList", "includeFuturesCmTradingPairList",
                "includeBstockTradingPairList"):
        v = gc.get(key)
        if v:
            return v
    return []


_AUM_CACHE = {}   # {resource_id: {"updated": ms, "total": float, "tail": float,
                 #                 "users": int, "tail_users": int, "cutoff": float}}


def aggregate_aum(api, resource_id, tail_start, updated_ms, state=None,
                  page_cap=500, chunk=4):
    """Sum Effective Net AUM across the whole leaderboard for AUM-based tracks.

    Binance exposes no AUM total, so we page through and sum `grade`. Rows are
    sorted by grade descending, so we stop at the first zero grade. Pages are
    fetched in parallel chunks to keep the total time under ~60s (cold).
    Result is cached in memory and in `state` keyed by the leaderboard
    updatedTime, so it's computed once per daily update.
    """
    from concurrent.futures import ThreadPoolExecutor

    key = str(resource_id)
    hit = _AUM_CACHE.get(key)
    if hit and hit.get("updated") == updated_ms and hit.get("tail") is not None:
        return hit
    if isinstance(state, dict):
        sc = (state.get("aum_cache") or {}).get(key)
        if sc and sc.get("updated") == updated_ms:
            _AUM_CACHE[key] = sc
            return sc

    def fetch(p):
        try:
            return api.leaderboard_page(resource_id, page_index=p, page_size=100)
        except Exception:
            return None

    total = 0.0
    top_sum = 0.0
    cutoff = None
    users = 0
    tail_users = 0
    pos = 0
    complete = False

    try:
        page = 1
        while page <= page_cap:
            pages = list(range(page, min(page + chunk, page_cap + 1)))
            with ThreadPoolExecutor(max_workers=len(pages)) as ex:
                batch = {p: ex.submit(fetch, p).result() for p in pages}

            done = False
            for p in sorted(batch):
                lb = batch[p]
                if not lb:
                    complete = True
                    done = True
                    break
                data = ((lb.get("resourceSummaryList") or {}).get("data")) or []
                if not data:
                    complete = True
                    done = True
                    break
                for r in data:
                    g = r.get("grade")
                    if g is None:
                        g = r.get("tradingVolume")
                    if g is None or float(g) <= 0:
                        done = True
                        complete = True
                        break
                    g = float(g)
                    pos += 1
                    total += g
                    users += 1
                    if pos < tail_start:
                        top_sum += g
                    else:
                        tail_users += 1
                    if pos == tail_start - 1:
                        cutoff = g
                if done:
                    break
                tr = (lb.get("resourceSummaryList") or {}).get("total") or 0
                if p * 100 >= tr:
                    complete = True
                    done = True
                    break
            if done:
                break
            page += chunk
    except Exception:
        complete = False

    if not complete:
        return None

    result = {
        "updated": updated_ms,
        "total": total,
        "tail": total - top_sum,
        "users": users,
        "tail_users": tail_users,
        "cutoff": cutoff,
    }
    _AUM_CACHE[key] = result
    if isinstance(state, dict):
        ac = dict(state.get("aum_cache") or {})
        ac[key] = result
        state["aum_cache"] = ac
    return result


def compute_track(api, group, act, state=None):
    """Compute estimator stats for ONE track (any shape: tail or top-N)."""
    gc = act.get("globalContent", {}) or {}
    rs = gc.get("rankingSetting", {}) or {}
    rp = gc.get("rewardPoolSetting", {}) or {}
    unit = (rp.get("unit") or "TOKEN").upper()
    pl = rs.get("rankingPrizeList") or []
    shape, tail_start, tail_pool, top_n = _tier_shape(pl)
    metric = metric_label(act)

    # how many leaderboard rows do we need?
    if metric == "AUM":
        pages = 1                        # only top-5 needed; AUM summed separately
    elif shape == "tail":
        need = tail_start - 1            # sum everything strictly below the tail
        pages = max(1, min(15, math.ceil(need / 100)))
    elif shape == "topN":
        need = top_n
        pages = max(1, min(15, math.ceil(need / 100)))
    else:
        return None

    rows = []
    eligible_users = None
    eligible_vol = None
    updated = None
    total = None
    for page in range(1, pages + 1):
        lb = api.leaderboard_page(act["id"], page_index=page, page_size=100)
        if not lb:
            break
        eligible_users = lb.get("eligibleUserCount")
        eligible_vol = lb.get("eligibleTradingVolume")
        updated = lb.get("updatedTime")
        batch = ((lb.get("resourceSummaryList") or {}).get("data")) or []
        rows.extend(batch)
        total = (lb.get("resourceSummaryList") or {}).get("total") or 0
        if page * 100 >= total:
            break
        time.sleep(0.05)

    price = api.token_price(unit)
    top_rows = sorted([r for r in rows if (r.get("sequence") or 0) <= 5],
                      key=lambda r: r.get("sequence") or 0)[:5]

    if shape == "tail":
        # AUM-based tracks (bStock): Binance exposes no AUM total, so sum
        # `grade` across the whole leaderboard (cached) to get the tail AUM.
        if metric == "AUM":
            cutoff_seq = tail_start - 1
            agg = aggregate_aum(api, act["id"], tail_start, updated, state=state)
            cap, cap_unit = _extract_cap(group, act, unit)
            cap_unit = cap_unit or unit
            cutoff_vol = None
            for r in rows:
                if (r.get("sequence") or 0) == cutoff_seq:
                    cutoff_vol = _metric_of(r)
            if agg and agg.get("cutoff") is not None:
                cutoff_vol = agg["cutoff"]
            if agg:
                tail_metric = max(0.0, agg["tail"])
                total_aum = agg["total"]
                tail_users = agg["tail_users"]
                rate = (tail_pool / tail_metric * 1000) if (tail_pool and tail_metric) else 0
                equal_split = (tail_pool / tail_users) if (tail_pool and tail_users) else 0
                eligible_vol_disp = total_aum
            else:
                # aggregation failed (rate-limited) → fall back to no numbers
                tail_metric = None
                total_aum = None
                tail_users = max(0, (eligible_users or 0) - cutoff_seq)
                rate = None
                equal_split = None
                eligible_vol_disp = None
            return {
                "group": group, "activity": act, "unit": unit, "price": price,
                "shape": shape, "metric": metric,
                "pool": (rp.get("rewardAmountList") or [{}])[0].get("amount"),
                "tail_pool": tail_pool, "tail_start": tail_start, "top_n": None,
                "cap": cap, "cap_unit": cap_unit, "prev_per_user": None,
                "aum_based": True,
                "eligible_users": eligible_users, "eligible_vol": eligible_vol_disp,
                "tail_users": tail_users,
                "tail_vol": tail_metric,
                "rank1000_vol": cutoff_vol,
                "rank1_vol": _metric_of(top_rows[0]) if top_rows else None,
                "top_rows": top_rows, "updated": updated,
                "ends": act.get("unpublishedTime") or act.get("taskExpiredTime"),
                "status": group.get("status"),
                "ended": group.get("status") == "UNPUBLISHED",
                "rate_per_1000": rate, "equal_split": equal_split,
                "qualify": gc.get("leaderboardQualifyThresholds"),
                "pairs": _pairs_of(act),
            }

        top_metric = sum(_metric_of(r) for r in rows
                         if (r.get("sequence") or 10**9) < tail_start)
        cutoff_seq = tail_start - 1
        cutoff_row = next((r for r in rows if (r.get("sequence") or 0) == cutoff_seq), None)
        tail_metric = max(0.0, (eligible_vol or 0) - top_metric)
        tail_users = max(0, (eligible_users or 0) - cutoff_seq)
        rate = (tail_pool / tail_metric * 1000) if (tail_pool and tail_metric) else 0
        equal_split = (tail_pool / tail_users) if (tail_pool and tail_users) else 0
        # per-user reward of the tier just above the tail (equal split)
        prev_per_user = None
        for t in pl:
            if t.get("end") == cutoff_seq and t.get("fixedAmount"):
                span = cutoff_seq - (t.get("start") or 1) + 1
                prev_per_user = t["fixedAmount"] / span
                break
        cap, cap_unit = _extract_cap(group, act, unit)
        cap_unit = cap_unit or unit
        cutoff_vol = _metric_of(cutoff_row) if cutoff_row else None
    elif shape == "topN":
        top_metric = sum(_metric_of(r) for r in rows
                         if (r.get("sequence") or 10**9) <= top_n)
        cutoff_row = next((r for r in rows if (r.get("sequence") or 0) == top_n), None)
        tail_metric = top_metric
        tail_users = top_n
        rate = (tail_pool / top_metric * 1000) if (tail_pool and top_metric) else 0
        equal_split = (tail_pool / top_n) if (tail_pool and top_n) else 0
        prev_per_user = None
        cap, cap_unit = None, unit     # top-N splits usually have no per-user cap
        cutoff_vol = _metric_of(cutoff_row) if cutoff_row else None
        tail_start = None
    else:
        return None

    return {
        "group": group,
        "activity": act,
        "unit": unit,
        "price": price,
        "shape": shape,
        "metric": metric,
        "pool": (rp.get("rewardAmountList") or [{}])[0].get("amount"),
        "tail_pool": tail_pool,
        "tail_start": tail_start,
        "top_n": top_n,
        "cap": cap,
        "cap_unit": cap_unit,
        "prev_per_user": prev_per_user,
        "eligible_users": eligible_users,
        "eligible_vol": eligible_vol,
        "tail_users": tail_users,
        "tail_vol": tail_metric,
        "rank1000_vol": cutoff_vol,
        "rank1_vol": _metric_of(top_rows[0]) if top_rows else None,
        "top_rows": top_rows,
        "updated": updated,
        "ends": act.get("unpublishedTime") or act.get("taskExpiredTime"),
        "status": group.get("status"),
        "ended": group.get("status") == "UNPUBLISHED",
        "rate_per_1000": rate,
        "equal_split": equal_split,
        "qualify": gc.get("leaderboardQualifyThresholds"),
        "pairs": _pairs_of(act),
    }


def _is_futures_track(act):
    t = (((act.get("i18nContent") or {}).get("title")) or "").lower()
    return "futures" in t


def _track_order_key(act):
    """Canonical ordering so track numbers are stable:
    1=Spot, 2=bStock, 3=TradFi, ... , Futures always LAST (merged)."""
    t = (((act.get("i18nContent") or {}).get("title")) or "").lower()
    for i, k in enumerate(("spot", "bstock", "tradfi")):
        if k in t:
            return i
    return 98 if not _is_futures_track(act) else 99


def group_tracks(raw_tracks):
    """Merge the futures sub-tracks (All Futures + Altcoin Futures) into ONE
    'Futures Competition' entry; others stay single.

    Ordered canonically: Spot → bStock → TradFi → (others) → Futures.
    """
    ordered = sorted(raw_tracks, key=_track_order_key)
    groups = []
    futures = []
    for t in ordered:
        if _is_futures_track(t):
            futures.append(t)
        else:
            groups.append({"kind": "single", "title": None, "tracks": [t]})
    if futures:
        groups.append({"kind": "multi", "title": "Futures Competition", "tracks": futures})
    return groups


def compute_all_tracks(api, group, activities, state=None):
    """Compute stats for every main track → list of entries.

    Each entry is {"kind": "single", "stats": {...}} or
    {"kind": "multi", "title": "...", "stats_list": [...]} (futures).
    """
    raw = identify_tracks(activities)
    entries = []
    for grp in group_tracks(raw):
        if grp["kind"] == "single":
            s = compute_track(api, group, grp["tracks"][0], state=state)
            if s:
                entries.append({"kind": "single", "stats": s})
        else:
            subs = []
            for act in grp["tracks"]:
                s = compute_track(api, group, act, state=state)
                if s:
                    subs.append(s)
            if subs:
                entries.append({"kind": "multi", "title": grp["title"], "stats_list": subs})
    return entries


def _extract_cap(group, act, unit):
    """Find the tail (rank 1001+) per-user cap for the main activity.

    Binance stores the real reward rules in two places:
      - the group's ruleContent (translated for standard campaigns), and
      - the activity's ruleContent / termAndConditionContent / reward*
        sections, which for multi-track campaigns (e.g. Traders League 4)
        reference RichTextI18nKey nodes that only resolve via the frontend
        i18n resource.

    We load the i18n resource, flatten every rule source, then scan for a cap
    that matches the reward unit (so sprint/other caps don't shadow it).
    """
    i18n = load_i18n()
    sources = []

    # group-level rules (standard token tournaments)
    sources.append(group_rule_text(group, i18n=i18n))

    # activity-level rules + terms (multi-track campaigns put everything here)
    ai18n = (act.get("i18nContent") or {}) if isinstance(act, dict) else {}
    for field in ("ruleContent", "termAndConditionContent",
                  "rewardStructureContent", "rewardAllocationContent"):
        v = ai18n.get(field)
        if isinstance(v, dict):
            raw = v.get("rule") or v.get("text")
            if raw:
                sources.append(rich_text_to_text(raw, i18n))
            # title/subtitle may themselves be i18n keys with cap text
            for sub in ("title", "subtitle", "sectionTitle", "sectionSubtitle"):
                sv = v.get(sub)
                if isinstance(sv, str):
                    sources.append((i18n or {}).get(sv, sv))

    combined = "\n".join(s for s in sources if s)
    return tail_cap_from_text(combined, prefer_unit=unit)


def track_title(act):
    """Human-readable title for one track (resolves the i18n key)."""
    t = resolve_title_key(((act.get("i18nContent") or {}).get("title") or ""),
                          load_i18n())
    t = re.sub(r"(Round)(\d)", r"\1 \2", t)   # "Round1" → "Round 1"
    t = re.sub(r"\s*-\s*", " — ", t)
    t = re.sub(r"\s+", " ", t).strip()
    if not t or is_i18n_key(t):
        return None
    return t


def _card_body(stats):
    """Card body below the 📐/🎯 header and above the footer."""
    L = []
    unit = stats["unit"]
    price = stats["price"]
    tail_pool = stats.get("tail_pool")
    shape = stats.get("shape", "tail")
    metric = stats.get("metric", "volume")
    top_n = stats.get("top_n")
    tail_start = stats.get("tail_start")

    # pool line
    pool = stats.get("pool")
    if shape == "topN" and top_n:
        if pool is not None:
            L.append(f"Prize pool {esc(fmt_num(pool, 0))} {unit} — top {top_n} proportional split")
    elif pool is not None:
        tail_txt = f" · tail pool {esc(fmt_num(tail_pool, 0))} {unit}" if tail_pool else ""
        L.append(f"Prize pool {esc(fmt_num(pool, 0))} {unit}{tail_txt}")
    pairs = " · ".join(stats.get("pairs") or [])
    if pairs:
        L.append(f"Pairs: <code>{esc(pairs[:400])}</code>")

    # --- top ranks ---
    rows = stats.get("top_rows") or []
    if rows:
        L.append("")
        L.append("🏆 <b>Top ranks</b>")
        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
        for r in rows:
            seq = r.get("sequence") or 0
            name = (r.get("nickName") or "—")
            val = _metric_of(r)
            medal = medals.get(seq, f"#{seq}")
            L.append(f"{medal} {esc(name)} — <code>{fmt_usd(val)}</code>")
        if stats.get("rank1000_vol") is not None:
            if shape == "topN":
                L.append(f"🎯 #{top_n} (cutoff) — <code>{fmt_usd(stats['rank1000_vol'])}</code>")
            else:
                L.append(f"🎯 #{tail_start - 1} (cutoff) — <code>{fmt_usd(stats['rank1000_vol'])}</code>")

    # --- totals ---
    L.append("")
    if stats.get("eligible_users") is not None:
        if stats.get("aum_based") and stats.get("eligible_vol") is not None:
            L.append(f"👥 <b>All eligible:</b> {stats['eligible_users']:,} users · "
                     f"<code>{fmt_usd(stats.get('eligible_vol') or 0)}</code> total {metric}")
        elif stats.get("aum_based"):
            L.append(f"👥 <b>All eligible:</b> {stats['eligible_users']:,} users")
        else:
            L.append(f"👥 <b>All eligible:</b> {stats['eligible_users']:,} users · "
                     f"<code>{fmt_usd(stats.get('eligible_vol') or 0)}</code> total {metric}")

    rate = stats.get("rate_per_1000")

    if shape == "topN":
        # --- top-N proportional structure ---
        L.append("")
        L.append(f"📉 <b>Top {top_n}:</b> proportional split · "
                 f"<code>{fmt_usd(stats.get('tail_vol'))}</code> combined {metric}")
        if rate:
            usd = f" (~{fmt_usd(rate * (price or 0))})" if price else ""
            L.append(f"📈 <b>Rate:</b> <code>{fmt_fixed(rate)} {unit}</code>{esc(usd)} per $1,000 {metric}")
        if tail_pool:
            L.append(f"🧮 <b>Rule:</b> (your {metric} ÷ top-{top_n} {metric}) × "
                     f"<code>{fmt_num(tail_pool, 0)} {unit}</code>")
    else:
        # --- tail (rank N+) structure ---
        L.append("")
        if stats.get("aum_based") and stats.get("tail_vol") is not None:
            L.append(f"📉 <b>Tail (rank {tail_start}+):</b> {stats.get('tail_users', 0):,} users · "
                     f"<code>{fmt_usd(stats.get('tail_vol') or 0)}</code> total {metric}")
        elif stats.get("aum_based"):
            L.append(f"📉 <b>Tail (rank {tail_start}+):</b> {stats.get('tail_users', 0):,} users · "
                     f"proportional by <b>Effective Net AUM</b>")
        else:
            L.append(f"📉 <b>Tail (rank {tail_start}+):</b> {stats.get('tail_users', 0):,} users · "
                     f"<code>{fmt_usd(stats.get('tail_vol') or 0)}</code> total {metric}")
        if rate:
            usd = f" (~{fmt_usd(rate * (price or 0))})" if price else ""
            L.append(f"📈 <b>Rate:</b> <code>{fmt_fixed(rate)} {unit}</code>{esc(usd)} per $1,000 {metric}")
        if tail_pool is not None:
            cap_txt = ""
            if stats.get("cap"):
                cap_txt = f", max <code>{fmt_fixed(stats['cap'], 4)} {esc(stats['cap_unit'] or unit)}</code>"
            L.append(f"🧮 <b>Rule:</b> (your {metric} ÷ tail {metric}) × "
                     f"<code>{fmt_num(tail_pool, 0)} {unit}</code>{cap_txt}")

    # --- examples ---
    if tail_pool is not None and stats.get("equal_split"):
        ex_vols = stats.get("example_volumes") or (60000, 30000, 10000, 5000, 1000)
        L.append("")
        if shape == "topN":
            L.append(f"🎁 <b>{metric} → reward</b> (× vs equal split of top-{top_n})")
        else:
            L.append(f"🎁 <b>{metric} → reward</b> (× vs old equal split)")
        for v in ex_vols:
            if stats.get("tail_vol"):
                raw_rw = v / stats["tail_vol"] * tail_pool
                rw = min(raw_rw, stats["cap"]) if stats.get("cap") else raw_rw
            else:
                rw = 0
            mult = rw / stats["equal_split"] if stats["equal_split"] else 0
            capped = " · CAPPED" if stats.get("cap") and rw >= stats["cap"] - 1e-9 else ""
            usd = f" (~{fmt_usd(rw * (price or 0))})" if price else ""
            L.append(f"<code>${v:,} → {fmt_fixed(rw, 4)} {unit}{esc(usd)} · {mult:.2f}×{capped}</code>")

    if stats.get("prev_per_user"):
        usd = f" (~{fmt_usd(stats['prev_per_user'] * (price or 0))})" if price else ""
        L.append(f"ℹ️ The tier just above (rank {tail_start - 1} and up) pays "
                 f"<code>{fmt_fixed(stats['prev_per_user'], 4)} {unit}</code>{esc(usd)} each "
                 f"— a different tier, not this one.")

    if stats.get("ended"):
        L.append("🏁 <i>This competition has ended — showing the final leaderboard.</i>")
    else:
        L.append(f"⚠️ <i>Live estimate — the {metric} keeps growing, so your share shrinks unless you keep trading.</i>")

    return L


def _card_footer(stats):
    L = [f"🕒 Updated: {esc(_fmt_ts(stats.get('updated')))} · ⏳ Ends: {esc(_fmt_ts(stats.get('ends')))}"]
    code = stats.get("group", {}).get("code") or ""
    if code:
        L.append(f"🔗 binance.com/en/activity/trading-competition/{esc(code)}")
    return L


def build_multi_card(group_title, stats_list):
    """One card containing several sub-tracks (e.g. Futures: All + Altcoin)."""
    if not stats_list:
        return ""
    L = [f"📐 <b>{esc(group_title)}</b>", "🎯 <b>Futures Competition</b>"]
    for s in stats_list:
        st = track_title(s.get("activity")) if s.get("activity") else None
        L.append("")
        if st:
            L.append(f"<b>── {esc(st)} ──</b>")
        L += _card_body(s)
    L.append("")
    L += _card_footer(stats_list[0])
    return "\n".join(L)


def build_tracks_message(entries):
    """One-line summary of every track in a multi-track campaign."""
    if not entries:
        return "No competition tracks found."
    first = entries[0]
    first_stats = first["stats"] if first["kind"] == "single" else first["stats_list"][0]
    group_title = title_for(first_stats)
    lines = [f"🎯 <b>{esc(group_title)}</b> — {len(entries)} track(s):", ""]
    medals = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    for i, e in enumerate(entries):
        num = medals[i] if i < len(medals) else f"{i + 1}."
        if e["kind"] == "single":
            s = e["stats"]
            tt = track_title(s.get("activity")) or "Track"
            unit = s["unit"]
            pool = s.get("pool")
            shape = s.get("shape", "tail")
            if shape == "topN":
                structure = f"top {s.get('top_n')} split"
            else:
                structure = f"rank {s.get('tail_start')}+ split"
            cap = f", cap {fmt_fixed(s['cap'], 4)} {s['cap_unit']}" if s.get("cap") else ", no cap"
            rate = s.get("rate_per_1000")
            rate_txt = f" · {fmt_num(rate)} {unit}/$1k" if rate else ""
            lines.append(f"{num} <b>{esc(tt)}</b> — {esc(fmt_num(pool, 0) if pool else '?')} {unit} "
                         f"({structure}{cap}){rate_txt}")
        else:
            subs = e["stats_list"]
            pools = " + ".join(esc(fmt_num(s.get('pool'), 0) if s.get('pool') else '?') for s in subs)
            units = {s["unit"] for s in subs}
            unit = next(iter(units)) if len(units) == 1 else "/".join(sorted(units))
            lines.append(f"{num} <b>{esc(e['title'])}</b> — {pools} {unit} "
                         f"({len(subs)} sub-competitions, top-300 splits)")
    lines.append("")
    lines.append("<i>/tracks &lt;code&gt; [count] — e.g. /tracks 1 for the first track only</i>")
    return "\n".join(lines)


def build_track_card(stats):
    """Full card for a single competition track (tail or top-N shape)."""
    L = [f"📐 <b>{esc(title_for(stats))}</b>"]
    tt = track_title(stats.get("activity")) if stats.get("activity") else None
    if tt and tt.lower() != title_for(stats).lower():
        L.append(f"🎯 <b>{esc(tt)}</b>")
    L += _card_body(stats)
    L.append("")
    L += _card_footer(stats)
    return "\n".join(L)
