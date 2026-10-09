"""P1: governance bridges, empty-table semantics, data_sources.md, merge conflicts."""
from __future__ import annotations

import os
import unittest
from pathlib import Path

import pandas as pd

from scripts.a_share_collector import render_data_sources_md
from scripts.merge.rules import merge_frames, pick_first_ok
from scripts.providers.base import SourceStatus, empty_genuine, failed, ok
from scripts.schema_bridge import (
    bridge_block_trade,
    bridge_forecast,
    bridge_holders,
    bridge_holdernumber,
    bridge_pledge,
    bridge_share_float,
)

RUN_NETWORK = os.environ.get("CA_NETWORK_TESTS") == "1"


class TestGovernanceBridges(unittest.TestCase):
    def test_holders_main(self):
        raw = pd.DataFrame(
            [
                {
                    "编号": 1,
                    "股东名称": "甲公司",
                    "持股数量": 1e8,
                    "持股比例": 54.5,
                    "股本性质": "流通A股",
                    "截至日期": "2026-06-30",
                    "公告日期": "2026-08-15",
                }
            ]
        )
        df = bridge_holders(raw, "600519.SH", float_mode=False)
        self.assertEqual(df.iloc[0]["end_date"], "20260630")
        self.assertEqual(df.iloc[0]["holder_name"], "甲公司")
        self.assertAlmostEqual(float(df.iloc[0]["hold_ratio"]), 54.5)

    def test_holdernumber(self):
        raw = pd.DataFrame(
            [{"股东户数统计截止日": "2026-06-30", "股东户数-本次": 296404, "股东户数公告日期": "2026-08-15"}]
        )
        df = bridge_holdernumber(raw, "600519.SH")
        self.assertEqual(int(df.iloc[0]["holder_num"]), 296404)
        self.assertEqual(df.iloc[0]["end_date"], "20260630")

    def test_block_trade_amount_scale(self):
        raw = pd.DataFrame(
            [
                {
                    "交易日期": "2025-09-12",
                    "成交价": 10.0,
                    "成交量": 1000,
                    "成交额": 2_000_000.0,  # 元 → 万元
                    "买方营业部": "买",
                    "卖方营业部": "卖",
                }
            ]
        )
        df = bridge_block_trade(raw, "000001.SZ")
        self.assertAlmostEqual(float(df.iloc[0]["amount"]), 200.0)

    def test_share_float(self):
        raw = pd.DataFrame(
            [{"解禁日期": "2026-12-01", "解禁数量": 100.0, "公告日期": "2026-01-01", "上市批次": 1}]
        )
        df = bridge_share_float(raw, "600519.SH")
        self.assertEqual(df.iloc[0]["float_date"], "20261201")

    def test_forecast_range_parse(self):
        raw = pd.DataFrame(
            [
                {
                    "_end_date": "20250630",
                    "公告日期": "2025-07-01",
                    "预告类型": "预增",
                    "预测数值": None,
                    "业绩变动": "预计净利润 1000万元至1500万元",
                    "预测指标": "归母净利润",
                }
            ]
        )
        df = bridge_forecast(raw, "300308.SZ")
        self.assertEqual(df.iloc[0]["end_date"], "20250630")
        self.assertAlmostEqual(float(df.iloc[0]["net_profit_min"]), 1000.0)
        self.assertAlmostEqual(float(df.iloc[0]["net_profit_max"]), 1500.0)

    def test_pledge_columns(self):
        raw = pd.DataFrame(
            [
                {
                    "股东名称": "张三",
                    "质押方": "某银行",
                    "质押股份数量": 1e6,
                    "占总股本比例": 1.2,
                    "占持股比例": 10.0,
                    "开始日期": "2025-01-01",
                    "结束日期": "2026-01-01",
                    "公告日期": "2025-01-02",
                    "状态": "未解押",
                }
            ]
        )
        df = bridge_pledge(raw, "688111.SH")
        self.assertEqual(df.iloc[0]["holder_name"], "张三")
        self.assertIn("pledge_amount", df.columns)


class TestEmptySemantics(unittest.TestCase):
    def test_block_trade_failed_not_genuine(self):
        w = pick_first_ok(
            "block_trade",
            [failed("block_trade", "akshare_dzjy", "timeout"), failed("block_trade", "em", "blocked")],
        )
        self.assertEqual(w.provenance.status, SourceStatus.SOURCE_FAILED)
        self.assertIn("do not treat as empty_genuine", w.provenance.note)

    def test_pledge_empty_genuine_distinct_from_failed(self):
        g = empty_genuine("pledge_detail", "akshare", "0 rows")
        f = failed("pledge_detail", "akshare", "HTTP 403")
        self.assertNotEqual(g.provenance.status, f.provenance.status)
        self.assertEqual(g.provenance.status, SourceStatus.EMPTY_GENUINE)

    def test_merge_conflict_keeps_primary(self):
        a = ok(
            "daily",
            pd.DataFrame({"trade_date": ["20250101"], "close": [100.0]}),
            "sina",
        )
        b = ok(
            "daily",
            pd.DataFrame({"trade_date": ["20250101"], "close": [120.0]}),
            "em",
        )
        m = merge_frames("daily", a, b, key="trade_date")
        self.assertAlmostEqual(float(m.df.iloc[0]["close"]), 100.0)
        self.assertTrue(any("close" in c for c in m.provenance.conflicts))


class TestDataSourcesMd(unittest.TestCase):
    def test_renders_gap_section_for_failed_pledge(self):
        prov = {
            "pledge_detail": {
                "cluster": "pledge_detail",
                "primary": "akshare",
                "status": "source_failed",
                "rows": 0,
                "error": "timeout",
                "note": "do NOT interpret as无质押",
                "conflicts": [],
            },
            "income": {
                "cluster": "income",
                "primary": "akshare",
                "status": "ok",
                "used": "akshare",
                "rows": 12,
                "note": "",
                "conflicts": [],
            },
        }
        md = render_data_sources_md(prov)
        self.assertIn("pledge_detail", md)
        self.assertIn("缺口", md)
        self.assertIn("source_failed", md)
        self.assertNotIn("无质押即事实", md)


class TestCapitalFlowWiring(unittest.TestCase):
    def test_record_cluster_maps_failed(self):
        from scripts import capital_flow as cf

        cf._CALL_ERRORS.clear()
        cf._CALL_EMPTY.clear()
        r = failed("block_trade", "akshare", "boom")
        df = cf._record_cluster("block_trade", r)
        self.assertTrue(df.empty)
        self.assertIn("block_trade", cf._CALL_ERRORS)
        self.assertNotIn("block_trade", cf._CALL_EMPTY)

    def test_record_cluster_maps_empty_genuine(self):
        from scripts import capital_flow as cf

        cf._CALL_ERRORS.clear()
        cf._CALL_EMPTY.clear()
        r = empty_genuine("block_trade", "akshare", "0 rows")
        cf._record_cluster("block_trade", r)
        self.assertIn("block_trade", cf._CALL_EMPTY)
        self.assertNotIn("block_trade", cf._CALL_ERRORS)


@unittest.skipUnless(RUN_NETWORK, "set CA_NETWORK_TESTS=1 for live P1 smoke")
class TestNetworkP1Smoke(unittest.TestCase):
    def test_holders_and_block_semantics(self):
        from scripts.providers import governance as gov

        h = gov.fetch_top10_holders("600519.SH")
        self.assertIn(h.provenance.status, (SourceStatus.OK, SourceStatus.PARTIAL))
        self.assertGreater(len(h.df), 0)
        self.assertIn("holder_name", h.df.columns)

        bt = gov.fetch_block_trade("600519.SH", days=90)
        self.assertIn(
            bt.provenance.status,
            (SourceStatus.OK, SourceStatus.EMPTY_GENUINE, SourceStatus.SOURCE_FAILED, SourceStatus.PARTIAL),
        )
        if bt.provenance.status == SourceStatus.SOURCE_FAILED:
            self.assertIn("大宗", bt.provenance.note or bt.provenance.error or "source_failed")

    def test_peer_manual_codes_path(self):
        from scripts.peer_collector import collect_peers

        df, md = collect_peers(
            "600519.SH",
            n=2,
            peer_codes=["000858.SZ"],  # 五粮液
            name_hint="贵州茅台",
        )
        self.assertFalse(df.empty, md[:500])
        codes = set(df["ts_code"].astype(str))
        self.assertIn("600519.SH", codes)
        self.assertIn("000858.SZ", codes)
        self.assertTrue("人工指定" in md or "peer-codes" in md or "P1 peer" in md)


if __name__ == "__main__":
    unittest.main()
