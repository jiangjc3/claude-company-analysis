"""Follow-up #3: stk_managers / stk_rewards / top_inst free-source wiring.

Offline unit tests + optional CA_NETWORK_TESTS=1 smoke.

Run:
    python -m unittest scripts.tests.test_deferred_fields -v
    CA_NETWORK_TESTS=1 python -m unittest scripts.tests.test_deferred_fields.TestNetworkDeferredFields -v
"""
from __future__ import annotations

import os
import unittest
from unittest.mock import MagicMock, patch

import pandas as pd

from scripts.providers import eastmoney_flow as em_flow
from scripts.providers import governance as gov
from scripts.providers.base import SourceStatus
from scripts.schema_bridge import (
    bridge_stk_managers,
    bridge_stk_rewards,
    bridge_top_inst_jgmmtj,
    bridge_top_inst_seats,
)

RUN_NETWORK = os.environ.get("CA_NETWORK_TESTS") == "1"


def _sample_gglb() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "SECUCODE": "300059.SZ",
                "SECURITY_CODE": "300059",
                "PERSON_NAME": "其实",
                "POSITION": "董事长,法定代表人,非独立董事",
                "PERSON_CODE": "1",
                "HOLD_NUM": 3042162258,
                "SALARY": 4922200,
                "POSITION_TYPE_CODE": "1",
                "SEX": "男",
                "HIGH_DEGREE": "博士",
                "AGE": "56",
                "RESUME": "...",
                "INCUMBENT_TIME": "2011-01-26至今",
                "IS_COMPARE": "1",
            },
            {
                "SECUCODE": "300059.SZ",
                "SECURITY_CODE": "300059",
                "PERSON_NAME": "独董甲",
                "POSITION": "独立董事",
                "PERSON_CODE": "2",
                "HOLD_NUM": None,
                "SALARY": None,
                "POSITION_TYPE_CODE": "2",
                "SEX": "女",
                "HIGH_DEGREE": "硕士",
                "AGE": "50",
                "RESUME": "...",
                "INCUMBENT_TIME": "2020-05-01至2023-04-30",
                "IS_COMPARE": "0",
            },
        ]
    )


class TestManagerRewardBridges(unittest.TestCase):
    def test_bridge_managers_incumbent_range(self):
        df = bridge_stk_managers(_sample_gglb(), "300059.SZ")
        self.assertEqual(len(df), 2)
        self.assertEqual(df.iloc[0]["name"], "其实")
        self.assertEqual(df.iloc[0]["begin_date"], "20110126")
        self.assertEqual(df.iloc[0]["end_date"], "")
        self.assertEqual(df.iloc[1]["begin_date"], "20200501")
        self.assertEqual(df.iloc[1]["end_date"], "20230430")
        self.assertEqual(df.iloc[0]["edu"], "博士")

    def test_bridge_rewards_skips_all_null(self):
        df = bridge_stk_rewards(_sample_gglb(), "300059.SZ")
        self.assertEqual(len(df), 1)
        self.assertEqual(df.iloc[0]["name"], "其实")
        self.assertAlmostEqual(float(df.iloc[0]["reward"]), 4922200.0)
        self.assertAlmostEqual(float(df.iloc[0]["hold_vol"]), 3042162258.0)

    def test_bridge_rewards_empty_when_no_figures(self):
        raw = _sample_gglb().copy()
        raw["SALARY"] = None
        raw["HOLD_NUM"] = None
        df = bridge_stk_rewards(raw, "300059.SZ")
        self.assertTrue(df.empty)


class TestTopInstBridges(unittest.TestCase):
    def test_jgmmtj_bridge(self):
        raw = pd.DataFrame(
            [
                {
                    "代码": "000002",
                    "名称": "万科A",
                    "机构买入总额": 1e8,
                    "机构卖出总额": 2e7,
                    "机构买入净额": 8e7,
                    "上榜日期": "2026-09-30",
                }
            ]
        )
        df = bridge_top_inst_jgmmtj(raw, "000002.SZ")
        self.assertEqual(len(df), 1)
        self.assertEqual(df.iloc[0]["trade_date"], "20260930")
        self.assertEqual(df.iloc[0]["exalter"], "机构专用")
        self.assertAlmostEqual(float(df.iloc[0]["net_buy"]), 8e7)

    def test_seat_bridge_filters_institution(self):
        raw = pd.DataFrame(
            [
                {"交易营业部名称": "机构专用", "买入金额": 1e7, "卖出金额": 1e6, "净额": 9e6},
                {"交易营业部名称": "某某证券营业部", "买入金额": 5e6, "卖出金额": 0, "净额": 5e6},
            ]
        )
        df = bridge_top_inst_seats(raw, "000002.SZ", "20260930")
        self.assertEqual(len(df), 1)
        self.assertEqual(df.iloc[0]["exalter"], "机构专用")


class TestFetchWithMocks(unittest.TestCase):
    def setUp(self):
        gov._EM_MGMT_CACHE.clear()

    def test_fetch_managers_ok(self):
        with patch.object(gov, "_fetch_em_company_management", return_value=_sample_gglb()):
            r = gov.fetch_stk_managers("300059.SZ")
        self.assertEqual(r.provenance.status, SourceStatus.OK)
        self.assertGreater(len(r.df), 0)
        self.assertNotEqual(r.provenance.status, SourceStatus.DEFERRED)

    def test_fetch_rewards_ok(self):
        with patch.object(gov, "_fetch_em_company_management", return_value=_sample_gglb()):
            r = gov.fetch_stk_rewards("300059.SZ")
        self.assertEqual(r.provenance.status, SourceStatus.OK)
        self.assertAlmostEqual(float(r.df.iloc[0]["reward"]), 4922200.0)

    def test_fetch_rewards_partial_when_salary_missing(self):
        raw = _sample_gglb().copy()
        raw["SALARY"] = None
        raw["HOLD_NUM"] = None
        with patch.object(gov, "_fetch_em_company_management", return_value=raw):
            r = gov.fetch_stk_rewards("300059.SZ")
        self.assertEqual(r.provenance.status, SourceStatus.PARTIAL)
        self.assertEqual(r.provenance.rows, 0)
        self.assertIn("年报", r.provenance.note or "")

    def test_fetch_managers_failed(self):
        with patch.object(gov, "_fetch_em_company_management", side_effect=RuntimeError("blocked")):
            r = gov.fetch_stk_managers("600519.SH")
        self.assertEqual(r.provenance.status, SourceStatus.SOURCE_FAILED)

    def test_top_inst_from_jgmmtj_fallback(self):
        jg = pd.DataFrame(
            [
                {
                    "代码": "000002",
                    "名称": "万科A",
                    "机构买入总额": 1e8,
                    "机构卖出总额": 2e7,
                    "机构买入净额": 8e7,
                    "上榜日期": "2026-09-30",
                }
            ]
        )
        fake_ak = MagicMock()
        fake_ak.stock_lhb_stock_detail_date_em.return_value = pd.DataFrame()
        fake_ak.stock_lhb_stock_detail_em.return_value = pd.DataFrame()
        fake_ak.stock_lhb_jgmmtj_em.return_value = jg
        with patch.object(em_flow, "_ak", return_value=fake_ak):
            r = em_flow.fetch_top_inst("000002.SZ", top_list_df=None, days=30)
        self.assertEqual(r.provenance.status, SourceStatus.OK)
        self.assertGreater(len(r.df), 0)
        self.assertEqual(r.df.iloc[0]["exalter"], "机构专用")
        self.assertNotEqual(r.provenance.status, SourceStatus.DEFERRED)

    def test_top_inst_empty_genuine(self):
        fake_ak = MagicMock()
        fake_ak.stock_lhb_stock_detail_date_em.return_value = pd.DataFrame()
        fake_ak.stock_lhb_jgmmtj_em.return_value = pd.DataFrame(
            columns=["代码", "机构买入总额", "机构卖出总额", "机构买入净额", "上榜日期"]
        )
        with patch.object(em_flow, "_ak", return_value=fake_ak):
            r = em_flow.fetch_top_inst("600519.SH", top_list_df=pd.DataFrame(), days=30)
        self.assertEqual(r.provenance.status, SourceStatus.EMPTY_GENUINE)


@unittest.skipUnless(RUN_NETWORK, "set CA_NETWORK_TESTS=1 for live deferred-fields smoke")
class TestNetworkDeferredFields(unittest.TestCase):
    def test_moutai_managers_live(self):
        gov._EM_MGMT_CACHE.clear()
        r = gov.fetch_stk_managers("600519.SH")
        self.assertIn(
            r.provenance.status,
            (SourceStatus.OK, SourceStatus.PARTIAL, SourceStatus.SOURCE_FAILED, SourceStatus.EMPTY_GENUINE),
        )
        if r.provenance.status == SourceStatus.OK:
            self.assertGreater(len(r.df), 0)
            self.assertIn("name", r.df.columns)
            self.assertIn("title", r.df.columns)

    def test_eastmoney_rewards_live(self):
        gov._EM_MGMT_CACHE.clear()
        r = gov.fetch_stk_rewards("300059.SZ")
        self.assertIn(
            r.provenance.status,
            (SourceStatus.OK, SourceStatus.PARTIAL, SourceStatus.SOURCE_FAILED, SourceStatus.EMPTY_GENUINE),
        )
        if r.provenance.status == SourceStatus.OK:
            self.assertTrue(r.df["reward"].notna().any())

    def test_top_inst_live_window(self):
        # Use a recent LHB name if detail window has activity; status must not be deferred.
        r = em_flow.fetch_top_inst("000002.SZ", days=45)
        self.assertNotEqual(r.provenance.status, SourceStatus.DEFERRED)
        self.assertIn(
            r.provenance.status,
            (SourceStatus.OK, SourceStatus.EMPTY_GENUINE, SourceStatus.SOURCE_FAILED, SourceStatus.PARTIAL),
        )


if __name__ == "__main__":
    unittest.main()
