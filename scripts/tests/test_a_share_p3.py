"""P3 tests: compare A-share-only, dual-reviewer gap prompts, attic gone, deferred gaps.

Run:
    python -m unittest scripts.tests.test_a_share_p3
"""
from __future__ import annotations

import unittest
from pathlib import Path

from scripts import compare
from scripts import manifest as manifest_mod
from scripts.codes import is_a_share_ticker, normalize_a_code
from scripts.providers import eastmoney_flow as em_flow
from scripts.providers import governance as gov
from scripts.providers.base import SourceStatus
from scripts.tests.test_compare_v8 import ANCHOR, ANCHOR_TICKER, CompareEnv, PEER, PEER_TICKER


class TestCodesAShareOnly(unittest.TestCase):
    def test_is_a_share(self):
        self.assertTrue(is_a_share_ticker("600519.SH"))
        self.assertTrue(is_a_share_ticker("300308"))
        self.assertFalse(is_a_share_ticker("0700.HK"))
        self.assertFalse(is_a_share_ticker("AAPL.US"))
        self.assertFalse(is_a_share_ticker("AAPL"))

    def test_normalize_rejects_hk_us(self):
        with self.assertRaises(ValueError):
            normalize_a_code("0700.HK")
        with self.assertRaises(ValueError):
            normalize_a_code("AAPL.US")


class TestCompareAShareHardening(CompareEnv):
    def test_parse_member_rejects_hk(self):
        with self.assertRaises(compare.CompareError) as ctx:
            compare.parse_member("腾讯:0700.HK:model")
        self.assertIn("A 股", str(ctx.exception))

    def test_parse_member_rejects_us(self):
        with self.assertRaises(compare.CompareError):
            compare.parse_member("苹果:AAPL.US:library")

    def test_create_group_rejects_non_a_ticker(self):
        with self.assertRaises(compare.CompareError):
            compare.create_group(
                anchor=ANCHOR,
                anchor_ticker=ANCHOR_TICKER,
                members=[
                    {"company": PEER, "ticker": PEER_TICKER, "source": "library"},
                    {"company": "腾讯", "ticker": "0700.HK", "source": "model"},
                ],
                slug="bad-hk",
                name="should fail",
                created="2026-10-09",
            )

    def test_create_group_normalizes_and_tags_market(self):
        group = compare.create_group(
            anchor=ANCHOR,
            anchor_ticker="002384",
            members=[{"company": PEER, "ticker": "999999.SZ", "source": "library"}],
            slug="p3-ashare",
            name="P3 A-share smoke",
            created="2026-10-09",
        )
        by = {m["company"]: m for m in group["members"]}
        self.assertEqual(by[ANCHOR]["ticker"], "002384.SZ")
        self.assertEqual(by[PEER]["market"], "A股")

    def test_library_candidates_skips_non_a_manifest(self):
        # leftover HK-shaped manifest must not appear as a compare candidate
        hk_dir = self.output / "腾讯控股"
        hk_dir.mkdir()
        manifest_mod.save(
            hk_dir,
            {
                "company": "腾讯控股",
                "ticker": "0700.HK",
                "market": "港股",
                "runs": [],
                "incremental_count": 0,
                "last_full_date": None,
                "next_disclosure_date": None,
                "compare_groups": [],
            },
        )
        names = {c["company"] for c in compare.library_candidates(ANCHOR)}
        self.assertIn(PEER, names)
        self.assertNotIn("腾讯控股", names)

    def test_assemble_rejects_group_with_hk_member(self):
        gdir = compare.group_dir("poison-hk")
        gdir.mkdir(parents=True)
        # Bypass create_group validation by writing a hostile group.json
        import json

        (gdir / compare.GROUP_NAME).write_text(
            json.dumps(
                {
                    "slug": "poison-hk",
                    "name": "poison",
                    "anchor": ANCHOR,
                    "created": "2026-10-09",
                    "members": [
                        {"company": ANCHOR, "ticker": ANCHOR_TICKER, "source": "anchor"},
                        {"company": PEER, "ticker": PEER_TICKER, "source": "library"},
                        {"company": "腾讯", "ticker": "0700.HK", "source": "model"},
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        with self.assertRaises(compare.CompareError):
            compare.assemble("poison-hk", today="2026-10-09")


class TestGovernanceFieldsNoLongerDeferred(unittest.TestCase):
    """Follow-up #3 landed free sources — status must not stay DEFERRED stubs."""

    def test_stk_managers_not_deferred_stub(self):
        from unittest.mock import patch

        import pandas as pd

        raw = pd.DataFrame(
            [
                {
                    "PERSON_NAME": "甲",
                    "POSITION": "董事长",
                    "SEX": "男",
                    "HIGH_DEGREE": "硕士",
                    "POSITION_TYPE_CODE": "1",
                    "INCUMBENT_TIME": "2020-01-01至今",
                    "SALARY": 1.0,
                    "HOLD_NUM": None,
                }
            ]
        )
        with patch.object(gov, "_fetch_em_company_management", return_value=raw):
            r = gov.fetch_stk_managers("600519.SH")
        self.assertNotEqual(r.provenance.status, SourceStatus.DEFERRED)
        self.assertEqual(r.provenance.status, SourceStatus.OK)

    def test_stk_rewards_not_deferred_stub(self):
        from unittest.mock import patch

        import pandas as pd

        raw = pd.DataFrame(
            [
                {
                    "PERSON_NAME": "甲",
                    "POSITION": "董事长",
                    "SEX": "男",
                    "HIGH_DEGREE": "硕士",
                    "POSITION_TYPE_CODE": "1",
                    "INCUMBENT_TIME": "2020-01-01至今",
                    "SALARY": 100.0,
                    "HOLD_NUM": 1000.0,
                }
            ]
        )
        with patch.object(gov, "_fetch_em_company_management", return_value=raw):
            r = gov.fetch_stk_rewards("600519.SH")
        self.assertNotEqual(r.provenance.status, SourceStatus.DEFERRED)
        self.assertEqual(r.provenance.status, SourceStatus.OK)

    def test_top_inst_not_partial_stub(self):
        import datetime as dt
        from unittest.mock import MagicMock, patch

        import pandas as pd

        day = dt.date.today().strftime("%Y%m%d")
        fake_ak = MagicMock()
        fake_ak.stock_lhb_stock_detail_date_em.return_value = pd.DataFrame()
        fake_ak.stock_lhb_stock_detail_em.return_value = pd.DataFrame(
            [{"交易营业部名称": "机构专用", "买入金额": 1.0, "卖出金额": 0.0, "净额": 1.0}]
        )
        fake_ak.stock_lhb_jgmmtj_em.return_value = pd.DataFrame()
        with patch.object(em_flow, "_ak", return_value=fake_ak):
            r = em_flow.fetch_top_inst(
                "600519.SH", pd.DataFrame({"trade_date": [day]}), days=30
            )
        self.assertNotEqual(r.provenance.status, SourceStatus.DEFERRED)
        self.assertEqual(r.provenance.status, SourceStatus.OK)


class TestDocsAndAttic(unittest.TestCase):
    def test_attic_removed(self):
        root = Path(__file__).resolve().parents[2]
        self.assertFalse((root / "attic").exists(), "plan D4: attic collectors must be deleted")

    def test_compliance_and_contributing_exist(self):
        root = Path(__file__).resolve().parents[2]
        self.assertTrue((root / "docs" / "data-sources-compliance.md").is_file())
        self.assertTrue((root / "CONTRIBUTING.md").is_file())
        text = (root / "docs" / "data-sources-compliance.md").read_text(encoding="utf-8")
        self.assertIn("stk_managers", text)
        self.assertIn("source_failed", text)

    def test_reviewer_prompts_cover_multisource_gaps(self):
        root = Path(__file__).resolve().parents[2]
        logic = (root / "agents" / "reviewer-logic.md").read_text(encoding="utf-8")
        delivery = (root / "agents" / "reviewer-delivery.md").read_text(encoding="utf-8")
        self.assertIn("1.6", logic)
        self.assertIn("多源缺口", logic)
        self.assertIn("source_failed", logic)
        self.assertIn("2.2", delivery)
        self.assertIn("多源缺口对读者撒谎", delivery)

    def test_network_nightly_workflow_optional(self):
        root = Path(__file__).resolve().parents[2]
        # Prefer landed Actions path; docs/ template is the fallback when PAT
        # lacks `workflow` scope and cannot push .github/workflows/*.
        landed = root / ".github" / "workflows" / "network-nightly.yml"
        template = root / "docs" / "optional-network-nightly.workflow.yml"
        path = landed if landed.is_file() else template
        self.assertTrue(path.is_file(), f"missing network nightly workflow at {path}")
        wf = path.read_text(encoding="utf-8")
        self.assertIn("CA_NETWORK_TESTS", wf)
        self.assertIn("continue-on-error: true", wf)
        self.assertIn("workflow_dispatch", wf)
        self.assertIn("TestSinaDailyLive", wf)


if __name__ == "__main__":
    unittest.main()
