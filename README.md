# Binance Spot Competition → Telegram Bot

A Telegram bot that scrapes Binance's **Spot Trading Competition** pages and posts a
**"Rank 1001+ proportional share"** reward-estimator card — showing which rank has which
volume, total volume, total users, the rank‑1000 cutoff volume, and your projected reward
for any trade size. It also lists **every running spot campaign** from Binance's Spot
Colosseum page and auto-detects **new campaigns** as they appear there.

Example card:

```
📐 XPL Trading Tournament
Main pool 3,200,000 XPL · tail pool 800,000 XPL
Pairs: XPL/USDT · XPL/USDC

🏆 Top ranks
🥇 关山飞渡 — $2,135,654
🥈 liangliang1 — $163,178
🥉 wudi523 — $129,854
#4 rabin092 — $59,077
#5 happyyybtc — $56,577
🎯 #1000 (cutoff) — $29,728

👥 All eligible: 26,331 users · $649,658,547 total volume

📉 Tail (rank 1001+): 25,331 users · $32,976,535 total volume
📈 Rate: 24.2597 XPL (~$2.16) per $1,000 volume
🧮 Rule: (your volume ÷ tail volume) × 800,000 XPL, max 500.0000 XPL

🎁 Volume → reward (× vs old equal split)
$60,000 → 500.0000 XPL (~$44.56) · 15.83× · CAPPED
$10,000 → 242.60 XPL (~$21.62) · 7.68×
$1,000 → 24.26 XPL (~$2.16) · 0.77×

ℹ️ Top-1000 tier pays 700.0000 XPL (~$62.39) each — a different tier, not this one.
⚠️ Live estimate — tail volume keeps growing, so your share shrinks unless you keep trading.

🕒 Updated: 2026-08-20 15:59 UTC · ⏳ Ends: 2026-08-27 06:00 UTC
🔗 binance.com/en/activity/trading-competition/spot-altcoin-festival-wave-XPL1
```

---

## How it works (data sources)

The bot uses **public** endpoints (the same ones the binance.com web app calls —
no API key, no login):

| Data | Endpoint |
|------|----------|
| Competition detail (reward tiers, pools, cap, pairs, dates) | `POST /bapi/composite/v1/public/growth-paas/resource/single` |
| Activities (Main pool + Sprint rounds) | `POST /bapi/composite/v1/public/growth-paas/resource/list` |
| Leaderboard (ranks, volumes, totals) | `POST /bapi/composite/v1/friendly/growth-paas/resource/summary/list` |
| Token price | `GET https://data-api.binance.vision/api/v3/ticker/price` |

For a token like `XPL` the bot resolves the competition code by trying patterns such as
`spot-altcoin-festival-wave-xpl1` (you can also pass the exact code from the Binance URL).

The card math (matches Binance's "Proportional Share Rewards Calculation Logic"):

```
tail volume     = eligibleTradingVolume − sum(volumes of ranks 1..1000)
tail users      = eligibleUserCount − 1000
rate per $1000  = tailPool / tailVolume × 1000
reward(vol)     = min( vol / tailVolume × tailPool , cap )
× vs equal split = reward(vol) / (tailPool / tailUsers)
```

---

## Setup

### 1. Install

```bash
cd spotcomp-bot
python -m venv .venv && source .venv/bin/activate   # optional
pip install -r requirements.txt
```

### 2. Create the bot

1. In Telegram, talk to **@BotFather** → `/newbot` → copy the **bot token**.
2. (Optional) Create a **channel**, add your bot as **administrator** so it can post.

### 3. Configure

```bash
cp config.example.json config.json
# edit config.json:
#   bot_token   → token from BotFather
#   channel_id  → "@your_channel"  (leave "" to only reply to commands)
#   watchlist   → tokens/codes to track, e.g. ["XPL", "PYTH"]
```

### 4. Run

```bash
python bot.py
```

The bot polls updates and, in a background thread, refreshes every `refresh_minutes`.
It posts a fresh card to the channel **only when the leaderboard volumes change**
(total volume, tail volume, rank‑1 / rank‑1000 cutoff, top‑5 ranks, user counts).
Binance's `updatedTime` stamp alone does **not** trigger a post. The last volumes are
remembered in `state.json`, so restarts won't cause duplicate posts.

To test without Telegram (prints the cards to the terminal):

```bash
python bot.py --cli XPL        # one competition
python bot.py --cli            # whole watchlist
```

---

## Commands

| Command | Effect |
|---------|--------|
| `/spotcomp XPL` | Full estimator card for a token or competition code |
| `/spotcomp spot-altcoin-festival-wave-pyth1` | …or by exact code |
| `/tracks CODE` | All tracks of a multi-track campaign (Spot / bStock / TradFi / Futures) |
| `/tracks CODE N` | First N tracks only (e.g. `/tracks CODE 1` = Spot track) |
| `/campaigns` | List **all running spot campaigns** (prize, end time, link) |
| `/campaigns TOKEN` | One campaign's card (same as `/spotcomp TOKEN`) |
| `/comps` | One-line status of all tracked competitions |
| `/watch TOKEN` | Start tracking a competition |
| `/unwatch TOKEN` | Stop tracking |
| `/now` | Refresh + post cards immediately |
| `/help` | Help |

---

## Config reference

```jsonc
{
  "bot_token": "…",            // required
  "channel_id": "@chan",       // optional auto-post target
  "refresh_minutes": 15,       // how often to re-check
  "watchlist": ["PYTH","RE"],  // starting list — auto-expanded when track_all_running is true
  "announce_new": true,        // post 🆕 message when a new competition appears on the Colosseum page
  "post_on_update_only": true, // post to channel only when leaderboard VOLUMES change
  "auto_remove_ended": true,   // auto-remove competitions from the watchlist once they end
  "track_all_running": true,   // auto-track EVERY running campaign (no manual /watch needed)
  "campaigns_cache_minutes": 30 // how long to cache the /campaigns result
}
```

### Where `/campaigns` and new-campaign detection come from

Everything runs off Binance's official **Spot Colosseum** hub
(`https://www.binance.com/en/events/spot-colosseum`) — the single page that lists all
currently-running spot campaigns. New campaigns appear there automatically, so:

- **`/campaigns`** reads that page and lists every running campaign (prize + end time).
- **Every refresh cycle** the bot re-checks the page. When a *new* campaign appears,
  it posts a 🆕 announcement **and starts tracking it automatically** — its cards get
  posted from then on. When one ends, it's removed (and announced 🏁).
- With **`track_all_running: true`** (default) the bot tracks **every** running
  campaign with zero setup — the watchlist is maintained fully automatically. Set it
  to `false` if you prefer to hand-pick competitions with `/watch`.

The page's HTML is bot-protected, so the bot reads it through a text-reader proxy
(no key needed). Binance occasionally region-blocks some reader IPs; if the page can't
be read, the bot logs a warning and simply skips that cycle rather than guessing.

State files (`watchlist.json`, `state.json`) are created automatically.

---

## Notes & disclaimer

- This uses **unofficial, undocumented** endpoints of Binance. They can change or rate-limit
  at any time. The bot is written defensively (retries + backoff) but has no guarantees.
- Data is a **live estimate**: the tail keeps growing, so the estimated share shrinks until
  settlement. Binance's own leaderboard is the source of truth.
- Respect Binance's Terms of Use; don't hammer the endpoints (keep `refresh_minutes` ≥ 5).
