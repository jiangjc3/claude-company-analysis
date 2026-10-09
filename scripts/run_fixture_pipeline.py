"""P2 smoke: dongshan fixture → assemble md → lint_v8 → HTML (no network, no LLM).

Usage (from skill root):
    python -m scripts.run_fixture_pipeline --out /tmp/ca-fixture-dongshan
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import assemble_report_v8 as render
from . import build_html
from . import lint_v8
from . import manifest as manifest_mod
from .tests import dongshan_fixture as fx
from .tests.test_assembly_v8 import write_run_dir


def run(out_dir: Path) -> dict:
    base = out_dir / "东山精密"
    if base.exists():
        raise SystemExit(f"refuse overwrite: {base}")
    run_dir = write_run_dir(base, fx.nodes(), fx.audit_result())
    (base / "data_snapshot.md").write_text("# 数据快照\n\nfixture\n", encoding="utf-8")
    (base / "peer_analysis.md").write_text("# Peer\n\nfixture\n", encoding="utf-8")
    (base / "capital_flow.md").write_text("# 资金流\n\nfixture\n", encoding="utf-8")
    (base / "sentiment.md").write_text("# 舆情底稿\n\nfixture\n", encoding="utf-8")
    (base / "data_sources.md").write_text(
        "# 数据来源与信息缺口\n\nfixture free-source path\n", encoding="utf-8"
    )
    (base / "audit_report.json").write_text(
        json.dumps(fx.audit_result(), ensure_ascii=False), encoding="utf-8"
    )
    (base / "red_flags.json").write_text(
        json.dumps({"red_flags": fx.script_flags()}, ensure_ascii=False), encoding="utf-8"
    )
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
    lint_result = lint_v8.lint_run(run_dir, artifacts_dir=base)
    _, nodes_blocks = build_html.load_v8_context(md_out, run_dir)
    html = build_html.build_html_v8(md_out, product, nodes=nodes_blocks, ticker="002384.SZ")
    html_path = Path(md_out).with_name("分析报告_dashboard.html")
    html_path.write_text(html, encoding="utf-8")
    (run_dir / "lint_report.md").write_text(lint_result.report, encoding="utf-8")
    return {
        "company_dir": str(base),
        "run_dir": str(run_dir),
        "md": str(md_out),
        "html": str(html_path),
        "lint_passed": lint_result.passed,
        "lint_exit_would_be": 0 if lint_result.passed else 1,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Dongshan fixture → md + HTML + lint_v8")
    ap.add_argument("--out", required=True, help="parent dir to create 东山精密/")
    args = ap.parse_args()
    info = run(Path(args.out))
    print(json.dumps(info, ensure_ascii=False, indent=2))
    return 0 if info["lint_passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
