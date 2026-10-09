"""P2 tests: disclosure sync for --review, fixture → md+HTML+lint_v8, A-share product docs.

Run:
    python -m unittest scripts.tests.test_a_share_p2
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from scripts import assemble_report_v8 as render
from scripts import build_html
from scripts import lint_v8
from scripts import manifest as manifest_mod
from scripts.a_share_collector import sync_manifest_disclosure
from scripts.tests import dongshan_fixture as fx
from scripts.tests.test_assembly_v8 import write_run_dir


class TestDisclosureCalendarP2(unittest.TestCase):
    def test_nearest_future_prefers_modify_then_pre_date(self):
        recs = [
            {"modify_date": "20261015", "pre_date": "20261001"},
            {"modify_date": None, "pre_date": "20261101"},
        ]
        self.assertEqual(
            manifest_mod.nearest_future_disclosure(recs, today="20261009"),
            "2026-10-15",
        )

    def test_bridge_shaped_df_via_helper(self):
        df = pd.DataFrame(
            [
                {"ts_code": "600519.SH", "pre_date": "20260901", "pre_ann_date": "20260901", "modify_date": None},
                {"ts_code": "600519.SH", "pre_date": "20261220", "pre_ann_date": "20261220", "modify_date": None},
            ]
        )
        self.assertEqual(
            manifest_mod.nearest_future_disclosure_from_df(df, today="20261009"),
            "2026-12-20",
        )

    def test_sync_disclosure_from_parquet_updates_manifest(self):
        with tempfile.TemporaryDirectory() as td:
            company = Path(td) / "贵州茅台"
            raw = company / "raw_data"
            raw.mkdir(parents=True)
            (company / "runs" / "2026-10-01" / "nodes").mkdir(parents=True)
            # minimal valid-enough manifest via create_run path pieces
            m = {
                "company": "贵州茅台",
                "ticker": "600519.SH",
                "market": "A股",
                "runs": [{"date": "2026-10-01", "type": "full"}],
                "incremental_count": 0,
                "last_full_date": "2026-10-01",
                "next_disclosure_date": None,
                "compare_groups": [],
            }
            manifest_mod.save(company, m)
            df = pd.DataFrame(
                [
                    {
                        "ts_code": "600519.SH",
                        "end_date": "20261231",
                        "pre_date": "20270328",
                        "pre_ann_date": "20270328",
                        "modify_date": None,
                    }
                ]
            )
            path = raw / "disclosure_date.parquet"
            df.to_parquet(path, index=False)
            picked, changed = manifest_mod.sync_disclosure_from_parquet(
                company, path, today="20261009"
            )
            self.assertEqual(picked, "2027-03-28")
            self.assertTrue(changed)
            self.assertEqual(manifest_mod.load(company)["next_disclosure_date"], "2027-03-28")
            # idempotent
            picked2, changed2 = manifest_mod.sync_disclosure_from_parquet(
                company, path, today="20261009"
            )
            self.assertEqual(picked2, "2027-03-28")
            self.assertFalse(changed2)

    def test_sync_manifest_disclosure_helper(self):
        with tempfile.TemporaryDirectory() as td:
            company = Path(td) / "fixture_co"
            raw = company / "raw_data"
            raw.mkdir(parents=True)
            manifest_mod.save(
                company,
                {
                    "company": "fixture_co",
                    "ticker": "000001.SZ",
                    "market": "A股",
                    "runs": [{"date": "2026-01-01", "type": "full"}],
                    "incremental_count": 0,
                    "last_full_date": "2026-01-01",
                    "next_disclosure_date": None,
                    "compare_groups": [],
                },
            )
            pd.DataFrame(
                [{"ts_code": "000001.SZ", "pre_date": "20270115", "modify_date": None}]
            ).to_parquet(raw / "disclosure_date.parquet", index=False)
            info = sync_manifest_disclosure(company, raw)
            self.assertEqual(info["next_disclosure_date"], "2027-01-15")
            self.assertTrue(info["manifest_updated"])


class TestFixtureReportPipelineP2(unittest.TestCase):
    """Dongshan fixture → assemble md → lint_v8 → HTML (Phase 3–6 machine path)."""

    def test_fixture_produces_md_html_and_lint_pass(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td) / "东山精密"
            run_dir = write_run_dir(base, fx.nodes(), fx.audit_result())
            # company-level artifacts (appendices / lint inputs)
            (base / "data_snapshot.md").write_text(
                "# 数据快照\n\n| 期 | 营收 |\n|---|---|\n| 2026Q1 | 148 亿 |\n",
                encoding="utf-8",
            )
            (base / "peer_analysis.md").write_text("# Peer\n\nok\n", encoding="utf-8")
            (base / "capital_flow.md").write_text("# 资金流\n\nok\n", encoding="utf-8")
            (base / "sentiment.md").write_text("# 舆情底稿\n\nok\n", encoding="utf-8")
            (base / "data_sources.md").write_text(
                "# 数据来源与信息缺口\n\n| 簇 | status |\n|---|---|\n| income | ok |\n",
                encoding="utf-8",
            )
            # company-level audit + red_flags (R18 sync); run_dir also has audit from write_run_dir
            (base / "audit_report.json").write_text(
                json.dumps(fx.audit_result(), ensure_ascii=False), encoding="utf-8"
            )
            (base / "red_flags.json").write_text(
                json.dumps({"red_flags": fx.script_flags()}, ensure_ascii=False),
                encoding="utf-8",
            )
            # disclosure on manifest for report stamp
            manifest_mod.save(
                base,
                {
                    "company": "东山精密",
                    "ticker": "002384.SZ",
                    "market": "A股",
                    "runs": [{"date": "2026-06-22", "type": "full"}],
                    "incremental_count": 0,
                    "last_full_date": "2026-06-22",
                    "next_disclosure_date": "2026-08-30",
                    "compare_groups": [],
                },
            )

            product, md_out = render.assemble_run(
                run_dir=run_dir,
                company="东山精密",
                date="2026-06-22",
                ticker="002384.SZ",
                artifacts_dir=base,
                next_disclosure_date="2026-08-30",
            )
            self.assertTrue(Path(md_out).exists())
            md_text = Path(md_out).read_text(encoding="utf-8")
            self.assertIn("东山精密", md_text)
            self.assertIn("下次预约披露日", md_text)

            result = lint_v8.lint_run(run_dir, artifacts_dir=base)
            failed = [
                r.name
                for r in result.rules
                if r.severity == lint_v8.FAIL and not r.passed and not r.skipped
            ]
            self.assertEqual(failed, [], result.report)
            self.assertTrue(result.passed)

            _, nodes_blocks = build_html.load_v8_context(md_out, run_dir)
            html = build_html.build_html_v8(
                md_out, product, nodes=nodes_blocks, ticker="002384.SZ"
            )
            html_path = run_dir / "analysis_dashboard.html"
            html_path.write_text(html, encoding="utf-8")
            self.assertGreater(html_path.stat().st_size, 1000)
            self.assertIn("决断", html)
            self.assertIn("002384", html)


class TestProductDocsP2(unittest.TestCase):
    def test_skill_and_readme_are_a_share_only(self):
        root = Path(__file__).resolve().parents[2]
        skill = (root / "SKILL.md").read_text(encoding="utf-8")
        readme = (root / "README.md").read_text(encoding="utf-8")
        self.assertIn("仅 A 股", skill)
        self.assertNotIn("市场(A股/美股/港股)", skill)
        self.assertTrue(
            any(tag in readme for tag in ("v8.10-p3", "v8.10--p3", "v8.10-p2", "v8.10--p2")),
            "README should badge/mention p2+",
        )
        self.assertIn("仅支持 A 股", readme)
        self.assertTrue("P0–P3" in readme or "P0–P2" in readme)
        # install messaging
        install = (root / "install.sh").read_text(encoding="utf-8")
        self.assertIn("仅 A 股", install)
        self.assertNotIn("支持 A 股 / 美股 / 港股", install)

    def test_monitor_rejects_non_a_share(self):
        from scripts import monitor

        with self.assertRaises(ValueError) as ctx:
            monitor._fetch_fresh_metrics("AAPL", "us")
        self.assertIn("仅支持 A 股", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
