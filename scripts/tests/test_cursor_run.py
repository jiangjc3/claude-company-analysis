"""P0 Cursor runtime: import-pack, emit-prompts, status (no network)."""
from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd
import yaml

from scripts import config
from scripts import cursor_run
from scripts.tests import dongshan_fixture as fx


class TestCursorResolveLocal(unittest.TestCase):
    def test_resolve_ticker_code(self):
        with mock.patch("scripts.providers.akshare_fundamentals.fetch_stock_basic") as fb:
            fb.return_value = type(
                "R",
                (),
                {"df": pd.DataFrame([{"name": "测试票", "ts_code": "300750.SZ"}])},
            )()
            info = cursor_run.resolve_query("300750.SZ")
        self.assertEqual(info["ticker"], "300750.SZ")
        self.assertEqual(info["company"], "测试票")


class TestCursorPackPipeline(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ca-cursor-"))
        self.addCleanup(lambda: shutil.rmtree(self.tmp, ignore_errors=True))
        self._old_output = config.OUTPUT_ROOT
        self._old_plugin = config.PLUGIN_ROOT
        config.OUTPUT_ROOT = self.tmp / "output"
        config.PLUGIN_ROOT = self.tmp
        config.OUTPUT_ROOT.mkdir(parents=True)
        self.addCleanup(self._restore)

    def _restore(self):
        config.OUTPUT_ROOT = self._old_output
        config.PLUGIN_ROOT = self._old_plugin

    def _make_pack(self) -> Path:
        pack = self.tmp / "pack"
        raw = pack / "raw_data"
        art = pack / "artifacts"
        raw.mkdir(parents=True)
        art.mkdir(parents=True)
        (raw / "_core_gate.json").write_text(
            json.dumps({"core_ok": True, "problems": []}), encoding="utf-8"
        )
        (raw / "_provenance.md").write_text("# prov\n", encoding="utf-8")
        for name in (
            "data_snapshot.md",
            "peer_analysis.md",
            "capital_flow.md",
            "technical_analysis.md",
            "data_sources.md",
            "audit_report.md",
        ):
            (art / name).write_text(f"# {name}\n", encoding="utf-8")
        (art / "audit_report.json").write_text(
            json.dumps(fx.audit_result(), ensure_ascii=False), encoding="utf-8"
        )
        (art / "red_flags.json").write_text(
            json.dumps({"red_flags": fx.script_flags()}, ensure_ascii=False), encoding="utf-8"
        )
        (art / "metrics.json").write_text("{}", encoding="utf-8")
        (art / "manifest.json").write_text(
            json.dumps(
                {"company": "东山精密", "ticker": "002384.SZ", "runs": []},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return pack

    def test_import_emit_status(self):
        pack = self._make_pack()
        rc = cursor_run.main(
            [
                "import-pack",
                "--pack",
                str(pack),
                "--company",
                "东山精密",
                "--ticker",
                "002384.SZ",
            ]
        )
        self.assertEqual(rc, 0)
        base = config.output_dir("东山精密")
        self.assertTrue((base / "data_snapshot.md").is_file())
        self.assertTrue((base / "red_flags.json").is_file())
        self.assertTrue((base / "raw_data" / "_core_gate.json").is_file())

        rc = cursor_run.main(["emit-prompts", "--company", "东山精密"])
        self.assertEqual(rc, 0)
        run_dir = cursor_run.latest_run_dir(base)
        self.assertIsNotNone(run_dir)
        assert run_dir is not None
        self.assertTrue((run_dir / "cursor_prompts" / "00-orchestrator.md").is_file())
        self.assertTrue((run_dir / "cursor_prompts" / "03a-node-quality.md").is_file())
        self.assertGreaterEqual(len(list((run_dir / "cursor_prompts").glob("*.md"))), 8)

        # Drop fixture nodes so status reports nodes_ready
        nodes_dir = run_dir / "nodes"
        nodes_dir.mkdir(parents=True, exist_ok=True)
        for node, block in fx.nodes().items():
            text = yaml.safe_dump(block, allow_unicode=True, sort_keys=False)
            body = fx.NODE_BODIES[node]
            (nodes_dir / f"node-{node}.md").write_text(
                f"```yaml\n{text}```\n\n{body}", encoding="utf-8"
            )

        rc = cursor_run.main(["status", "--company", "东山精密"])
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
