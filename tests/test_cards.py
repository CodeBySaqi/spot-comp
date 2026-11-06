"""Offline unit tests for cards.py (card math + formatting).

No network: the Binance API is replaced with a small fake and load_i18n
is stubbed, so the suite runs anywhere with just pytest.
"""

import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

import cards
from binance_api import tail_cap_from_text


# ---------------------------------------------------------------- fixtures


def _lb_page(page_index, total=1000, start_seq=1):
    rows = []
    for i in range(100):
        seq = (page_index - 1) * 100 + i + 1
        rows.append(
            {
                "sequence": seq,
                "nickName": f"user{seq}",
                "tradingVolume": 500_000 - seq * 400,  # rank1 499600 … rank1000 100000
            }
        )
    return {
        "eligibleUserCount": 26_331,
        "eligibleTradingVolume": 649_658_547.0,
        "updatedTime": int(datetime.datetime(2026, 8, 20, 15, 59,
                                             tzinfo=datetime.timezone.utc).timestamp() * 1000),
        "resourceSummaryList": {"data": rows, "total": total},
    }


class FakeApi:
    def __init__(self):
        self.pages_fetched = []

    def leaderboard_page(self, resource_id, page_index, page_size):
        self.pages_fetched.append(page_index)
        if page_index > 10:
            return None
        return _lb_page(page_index)

    def token_price(self, unit):
        return 0.0891


def _activity():
    return {
        "id": "act-1",
        "i18nContent": {"title": "Spot Trading Competition - Main"},
        "globalContent": {
            "rankingSetting": {
                "rankingPrizeList": [
                    {"start": 1, "end": 1000, "fixedAmount": 700_000},
                    {"start": 1001, "end": None, "fixedAmount": 800_000},
                ]
            },
            "rewardPoolSetting": {
                "unit": "XPL",
                "rewardAmountList": [{"amount": 4_000_000}],
            },
            "includeSpotTradingPairList": ["XPL/USDT"],
        },
        "unpublishedTime": int(datetime.datetime(2026, 8, 27, 6, 0,
                                                tzinfo=datetime.timezone.utc).timestamp() * 1000),
    }


def _group():
    # Binance rich-text shape: {"config": {"content": ...}}
    rule = json.dumps([{"config": {"content": "Rewards are capped at 500 XPL per user."}}])
    return {
        "code": "spot-altcoin-festival-wave-xpl1",
        "status": "PUBLISHED",
        "i18nContent": {"homepage": {"ruleContent": {"rule": rule}}},
    }


@pytest.fixture()
def stats(monkeypatch):
    monkeypatch.setattr(cards, "load_i18n", lambda force=False: {})
    return cards.compute(FakeApi(), _group(), [_activity()])


# ---------------------------------------------------------------- formatting


def test_fmt_usd():
    assert cards.fmt_usd(29_728) == "$29,728.00"


def test_fmt_num_strips_float_zeros():
    assert cards.fmt_num(242.6) == "242.6"
    assert cards.fmt_num(4_000_000, 0) == "4,000,000"


def test_fmt_fixed_keeps_decimals():
    assert cards.fmt_fixed(500) == "500.0000"
    assert cards.fmt_fixed(24.2597) == "24.2597"


def test_esc_keeps_quotes():
    # quote=False: quotes stay as-is (Telegram HTML parse mode)
    assert cards.esc('<b>"hi" & bye</b>') == '&lt;b&gt;"hi" &amp; bye&lt;/b&gt;'
    assert cards.esc('<a href="x">y & z</a>') == '&lt;a href="x"&gt;y &amp; z&lt;/a&gt;'


def test_fmt_price_val_boundaries():
    assert cards.fmt_price_val(1234.5) == "$1,234.50"
    assert cards.fmt_price_val(1.23456) == "$1.2346"
    assert cards.fmt_price_val(0.001234) == "$0.001234"
    assert cards.fmt_price_val(0.0000123) == "$0.0000123"
    assert cards.fmt_price_val(-5) == "-$5"  # negatives strip too


# ---------------------------------------------------------------- tiers


def _act_with_pl(pl):
    return {"globalContent": {"rankingSetting": {"rankingPrizeList": pl}}}


def test_get_tier_for_rank():
    pl = [
        {"start": 1, "end": 1000, "fixedAmount": 700_000},
        {"start": 1001, "end": None, "fixedAmount": 800_000},
    ]
    assert cards.get_tier_for_rank(pl, 500)["fixedAmount"] == 700_000
    assert cards.get_tier_for_rank(pl, 1001)["fixedAmount"] == 800_000
    assert cards.get_tier_for_rank(pl, 50000)["fixedAmount"] == 800_000


def test_get_tail_tier():
    pl = [
        {"start": 1, "end": 1000, "fixedAmount": 700_000},
        {"start": 1001, "end": None, "fixedAmount": 800_000},
    ]
    tail = cards.get_tail_tier(_act_with_pl(pl))
    assert tail["start"] == 1001
    assert cards.get_tail_tier(
        _act_with_pl([{"start": 1, "end": 100, "fixedAmount": 10}])) is None


def test_tier_shape_classification():
    tail_pl = [{"start": 1, "end": 1000, "fixedAmount": 1},
               {"start": 1001, "end": None, "fixedAmount": 2}]
    assert cards._tier_shape(tail_pl)[0] == "tail"
    topn_pl = [{"start": 1, "end": 300, "fixedAmount": 5}]
    shape, _, pool, top_n = cards._tier_shape(topn_pl)
    assert (shape, pool, top_n) == ("topN", 5, 300)
    fixed_pl = [{"start": 1, "end": 10, "fixedAmount": 1},
                {"start": 11, "end": 20, "fixedAmount": 2}]
    assert cards._tier_shape(fixed_pl)[0] == "fixed"


def test_pick_main_activity():
    other = {"i18nContent": {"title": "Sprint Round 1"},
             "globalContent": {"rankingSetting": {"rankingPrizeList": []}}}
    main = _activity()
    assert cards.pick_main_activity([other, main]) is main


def test_metric_label():
    assert cards.metric_label({"i18nContent": {"title": "bStock Trading Competition"}}) == "AUM"
    assert cards.metric_label({"i18nContent": {"title": "Futures Trading Competition"}}) == "eligible volume"
    assert cards.metric_label({"i18nContent": {"title": "Spot Trading Competition"}}) == "volume"


# ---------------------------------------------------------------- codes & dates


def test_token_from_code():
    assert cards.token_from_code("spot-altcoin-festival-wave-xpl1") == "XPL"
    assert cards.token_from_code("spot-altcoin-festival-wave-rez-r1") == "REZ"
    assert cards.token_from_code("something-else") is None


def test_humanize_code():
    assert cards.humanize_code("202609tradersleague4") == "Traders League 4"
    assert cards.humanize_code("spot-trading-festival-wave-r3") == "Round 3"
    assert cards.humanize_code("") is None


def test_extract_reward_date_exact():
    assert cards.extract_reward_date(
        "Rewards will be distributed by 2026-09-17 to eligible users") == "2026-09-17"


def test_extract_reward_date_relative():
    ends = int(datetime.datetime(2026, 8, 27, 6, 0,
                                 tzinfo=datetime.timezone.utc).timestamp() * 1000)
    assert cards.extract_reward_date(
        "Rewards will be distributed within 7 days after the competition ends",
        ends_ms=ends) == "2026-09-03"


def test_extract_reward_date_fallback_and_tba():
    ends = int(datetime.datetime(2026, 8, 27, 6, 0,
                                 tzinfo=datetime.timezone.utc).timestamp() * 1000)
    assert cards.extract_reward_date("some rules without dates", ends_ms=ends) == "2026-09-10"
    assert cards.extract_reward_date("") == "TBA"


def test_tail_cap_from_text():
    assert tail_cap_from_text("capped at 500 XPL per user", prefer_unit="XPL") == (500.0, "XPL")
    assert tail_cap_from_text("maximum of 250 USDT per user") == (250.0, "USDT")
    assert tail_cap_from_text("no cap mentioned here") == (None, None)


# ---------------------------------------------------------------- tables & misc


def test_format_ascii_table():
    out = cards.format_ascii_table(["Name", "Ends"], [["XPL", "2026-08-27"]])
    assert out.startswith("┌") and out.endswith("┘")
    assert "XPL" in out and "2026-08-27" in out


def test_volume_fingerprint_stable():
    s1 = {"eligible_users": 10, "eligible_vol": 100.0, "tail_users": 5,
          "tail_vol": 50.0, "rank1_vol": 30.0, "rank1000_vol": 1.0,
          "top_rows": [{"sequence": 1, "tradingVolume": 30.0}]}
    fp = cards.volume_fingerprint(s1)
    assert "u:10" in fp and "r1:30.00" in fp
    assert cards.volume_fingerprint(s1) == fp
    assert cards.volume_fingerprint({}) != fp


# ---------------------------------------------------------------- compute + card


def test_compute_tail_math(stats):
    # sum of rank 1..1000 volumes: 1000 * (499600 + 100000) / 2
    assert stats["tail_vol"] == pytest.approx(649_658_547.0 - 299_800_000.0)
    assert stats["tail_users"] == 25_331
    assert stats["rate_per_1000"] == pytest.approx(800_000 / stats["tail_vol"] * 1000)
    assert stats["equal_split"] == pytest.approx(800_000 / 25_331)
    assert stats["top1000_per_user"] == pytest.approx(700.0)
    assert (stats["cap"], stats["cap_unit"]) == (500.0, "XPL")
    assert stats["rank1_vol"] == 499_600
    assert stats["rank1000_vol"] == 100_000


def test_build_card_content(stats):
    card = cards.build_card(stats)
    assert "📐 <b>XPL Trading Competition</b>" in card
    assert "🧮 <b>Rule:</b> (your volume ÷ tail volume) × <code>800,000 XPL</code>, " \
           "max <code>500.0000 XPL</code>" in card
    assert "📈 <b>Rate:</b>" in card
    assert "🕒 Updated: 2026-08-20 15:59 UTC · ⏳ Ends: 2026-08-27 06:00 UTC" in card
    assert "🎯 #1000 (cutoff)" in card


def test_build_card_caps_large_volume(stats):
    stats["example_volumes"] = (2_000_000,)
    card = cards.build_card(stats)
    assert "500.0000 XPL" in card
    assert "CAPPED" in card
