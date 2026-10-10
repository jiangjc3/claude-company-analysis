"""Sina / legacy daily quote path (P3: no TushareCollector).

Historically this file patched TushareCollector.daily() to force a Pro-empty →
legacy fallback. Tushare is gone; sina_quote / legacy_quote is the primary daily
path. Offline unit coverage lives in test_legacy_quote.py; this module only keeps
an optional live smoke behind CA_NETWORK_TESTS=1.

Run:
    CA_NETWORK_TESTS=1 python -m unittest scripts.tests.test_daily_fallback
"""
from __future__ import annotations

import os
import unittest

from scripts.legacy_quote import get_daily_history_legacy

RUN_NETWORK = os.environ.get("CA_NETWORK_TESTS") == "1"


@unittest.skipUnless(RUN_NETWORK, "set CA_NETWORK_TESTS=1 to hit sina kline")
class TestSinaDailyLive(unittest.TestCase):
    def test_bj_code_schema(self):
        # API takes datalen (trading days), not years — ~250 ≈ 1 calendar year.
        df = get_daily_history_legacy("920522.BJ", datalen=250)
        self.assertGreater(len(df), 0, "sina kline should return rows for BJ sample")
        expected = {
            "ts_code", "trade_date", "open", "high", "low", "close",
            "pre_close", "change", "pct_chg", "vol", "amount",
        }
        self.assertTrue(expected.issubset(set(df.columns)))
        self.assertEqual(df["ts_code"].iloc[0], "920522.BJ")


class TestTushareShimStillDead(unittest.TestCase):
    def test_tushare_collector_raises(self):
        from scripts.tushare_collector import TushareCollector

        with self.assertRaises(RuntimeError):
            TushareCollector()


if __name__ == "__main__":
    unittest.main()
