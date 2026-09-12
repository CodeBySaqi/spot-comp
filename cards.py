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

import html as _html
import json
import re
import time

from binance_api import group_rule_text, is_i18n_key, tail_cap_from_text

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


def compute(api, group, activities):
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
        time.sleep(0.15)

    sum_top1000 = sum((r.get("tradingVolume") or r.get("grade") or 0)
                      for r in rows
                      if (r.get("sequence") or 10**9) <= TOP1000_CUTOFF)
    rank1000_row = next((r for r in rows if (r.get("sequence") or 0) == TOP1000_CUTOFF), None)
    rank1_row = next((r for r in rows if (r.get("sequence") or 0) == 1), None)

    tail_users = max(0, (eligible_users or 0) - TOP1000_CUTOFF)
    tail_vol = max(0.0, (eligible_vol or 0) - sum_top1000)

    price = api.token_price(unit)

    # --- CAP DETECTION (FIXED) ---
    # Only use cap if explicitly found in rules text.
    # DO NOT fall back to equal_split as cap — that makes everything appear "CAPPED".
    cap, cap_unit = tail_cap_from_text(group_rule_text_for(group))
    # cap stays None if not found — means NO per-user cap for this competition
    cap_unit = cap_unit or unit

    rate_per_1000 = (tail_pool / tail_vol * 1000) if (tail_pool and tail_vol) else 0
    equal_split = (tail_pool / tail_users) if (tail_pool and tail_users) else 0

    return {
        "group": group,
        "activity": act,
        "activities": activities,
        "unit": unit,
        "price": price,
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


_GENERIC_WORDS = {
    "spot", "altcoin", "festival", "wave", "waves", "trading",
    "competition", "tournament", "round", "the", "season", "carnival",
}
_COMPOUND_WORDS = {
    "tradersleague": "Traders League",
}


def token_from_code(code):
    """Extract a token symbol from a wave-style code (e.g. ...wave-REZ-R1 → REZ)."""
    m = re.search(r"wave-([A-Za-z0-9]+?)(?:-?[Rr]?\d+)?$", code or "")
    if m:
        tok = m.group(1).upper()
        if len(tok) >= 2 and not tok.isdigit():
            return tok
    return None


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
        part = re.sub(r"^\d{4,}", "", part)          # drop date-ish prefixes (202609)
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
            L.append("🎁 <b>Volume → reward</b> (× vs old equal split)")
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

        # Button uses full code so /spotcomp resolves correctly
        keyboard_buttons.append([{
            "text": f"📊 {display}",
            "callback_data": f"spotcomp:{c.code}"
        }])

    reply_markup = json.dumps({
        "inline_keyboard": keyboard_buttons
    })

    lines.append("<i>👆 Tap a button below to see the full card</i>")

    return "\n".join(lines).rstrip(), reply_markup
