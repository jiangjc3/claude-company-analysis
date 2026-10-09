"""P0: schema_bridge, merge/provenance, check_env without Tushare, optional network smoke."""
from __future__ import annotations

import json
import os
import unittest
from pathlib import Path

import pandas as pd

from scripts.codes import normalize_a_code, to_em_secid
from scripts.merge.rules import pick_first_ok
from scripts.providers.base import SourceStatus, empty_genuine, failed, ok
from scripts.schema_bridge import (
    CRITICAL_BALANCE,
    CRITICAL_INCOME,
    bridge_balancesheet,
    bridge_income,
    missing_critical,
)

FIXTURES = Path(__file__).parent / "fixtures" / "a_share_em"
RUN_NETWORK = os.environ.get("CA_NETWORK_TESTS") == "1"


class TestCodes(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(normalize_a_code("600519"), "600519.SH")
        self.assertEqual(normalize_a_code("300308.SZ"), "300308.SZ")
        self.assertEqual(to_em_secid("600519.SH"), "SH600519")


class TestSchemaBridge(unittest.TestCase):
    def test_income_bridge_critical(self):
        raw = pd.DataFrame(json.loads((FIXTURES / "income_sample.json").read_text(encoding="utf-8")))
        df = bridge_income(raw)
        self.assertEqual(df.iloc[0]["ts_code"], "600519.SH")
        self.assertEqual(df.iloc[0]["end_date"], "20250630")
        self.assertEqual(missing_critical(df, CRITICAL_INCOME), [])
        self.assertAlmostEqual(float(df.iloc[0]["invest_income"]), 50.0)

    def test_balance_bridge_contract_liab(self):
        raw = pd.DataFrame(json.loads((FIXTURES / "balance_sample.json").read_text(encoding="utf-8")))
        df = bridge_balancesheet(raw)
        self.assertEqual(missing_critical(df, CRITICAL_BALANCE), [])
        self.assertAlmostEqual(float(df.iloc[0]["contract_liab"]), 27.64)
        self.assertAlmostEqual(float(df.iloc[0]["oth_ncl"]), 12.38)


class TestMergeProvenance(unittest.TestCase):
    def test_pick_first_ok_prefers_rows(self):
        a = failed("daily", "akshare", "timeout")
        b = ok("daily", pd.DataFrame({"trade_date": ["20250101"], "close": [1.0]}), "sina_kline")
        w = pick_first_ok("daily", [a, b])
        self.assertEqual(w.provenance.used, "sina_kline")
        self.assertEqual(w.provenance.status, SourceStatus.OK)

    def test_all_failed_not_empty_genuine(self):
        w = pick_first_ok("daily", [failed("daily", "a", "e1"), failed("daily", "b", "e2")])
        self.assertEqual(w.provenance.status, SourceStatus.SOURCE_FAILED)
        self.assertIn("do not treat as empty_genuine", w.provenance.note)

    def test_empty_genuine_distinct(self):
        w = pick_first_ok("anns", [empty_genuine("anns", "cninfo", "no notices")])
        self.assertEqual(w.provenance.status, SourceStatus.EMPTY_GENUINE)


class TestCheckEnv(unittest.TestCase):
    def test_check_env_no_tushare_required(self):
        from scripts import check_env, config

        # Ensure missing token does not fail the check by itself
        old = config.TUSHARE_TOKEN
        try:
            config.TUSHARE_TOKEN = None
            code = check_env.check()
            self.assertEqual(code, 0)
        finally:
            config.TUSHARE_TOKEN = old


class TestTushareShim(unittest.TestCase):
    def test_collector_raises(self):
        from scripts.tushare_collector import TushareCollector

        with self.assertRaises(RuntimeError):
            TushareCollector()


class TestUsHkStubs(unittest.TestCase):
    def test_us_raises(self):
        from scripts.us_collector import USCollector

        with self.assertRaises(RuntimeError):
            USCollector()

    def test_hk_raises(self):
        from scripts.hk_collector import HKCollector

        with self.assertRaises(RuntimeError):
            HKCollector()


@unittest.skipUnless(RUN_NETWORK, "set CA_NETWORK_TESTS=1 to run live collector smoke")
class TestNetworkSmoke(unittest.TestCase):
    def test_moutai_core_tables(self):
        from scripts.a_share_collector import AShareCollector

        c = AShareCollector()
        bundle, prov = c.collect_all("600519.SH", start_year=2022)
        ok_gate, problems = c.core_gate(prov)
        self.assertTrue(ok_gate, problems)
        for k in ("income", "balancesheet", "cashflow", "fina_indicator", "daily"):
            self.assertGreater(len(bundle[k]), 0, k)


if __name__ == "__main__":
    unittest.main()
