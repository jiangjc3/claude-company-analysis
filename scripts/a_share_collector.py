"""A-share collector facade — free multi-source, Tushare-shaped parquet bundle (P0).

Usage:
    python3 -m scripts.a_share_collector 600519.SH --name 贵州茅台
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

from . import config
from .codes import normalize_a_code
from .providers import akshare_fundamentals as akf
from .providers import cninfo as cninfo_prov
from .providers import sina_quote
from .providers.base import ClusterResult, SourceStatus, deferred


CORE_CLUSTERS = ("income", "balancesheet", "cashflow", "fina_indicator", "daily")


class AShareCollector:
    """Collect A-share bundle with provenance; no Tushare token."""

    def collect_all(self, ts_code: str, start_year: int = 2022) -> tuple[dict[str, pd.DataFrame], dict[str, Any]]:
        code = normalize_a_code(ts_code)
        results: dict[str, ClusterResult] = {}

        results["stock_basic"] = akf.fetch_stock_basic(code)
        results["income"] = akf.fetch_income(code)
        results["balancesheet"] = akf.fetch_balancesheet(code)
        results["cashflow"] = akf.fetch_cashflow(code)
        results["fina_indicator"] = akf.fetch_fina_indicator(code)

        # quotes: sina primary; akshare hist as secondary later (P1)
        daily = sina_quote.fetch_daily(code, years=max(3, dt_years_since(start_year)))
        results["daily"] = daily
        results["daily_basic"] = akf.fetch_daily_basic(code, daily.df if not daily.df.empty else None)

        results["anns"] = cninfo_prov.fetch_anns(code, days=90)

        # P0 deferred clusters (P1) — explicit, not silent empty
        for name, reason in (
            ("top10_holders", "P1: holders provider"),
            ("top10_floatholders", "P1: holders provider"),
            ("pledge_detail", "P1: pledge provider"),
            ("stk_managers", "P1: managers provider"),
            ("stk_rewards", "P1: rewards provider"),
            ("stk_holdernumber", "P1: holder-number provider"),
            ("repurchase", "P1: repurchase provider"),
            ("forecast_vip", "P1: earnings-preview provider"),
            ("express_vip", "P1: express provider"),
            ("fina_mainbz", "P1: main-business mix (or Phase 2 PDF)"),
            ("dividend", "P1: dividend provider"),
            ("disclosure_date", "P1: disclosure calendar"),
            ("share_float", "P1: share-float provider"),
            ("block_trade", "P1: block-trade provider"),
        ):
            results[name] = deferred(name, reason)

        bundle = {k: v.df.copy() for k, v in results.items()}
        # filter statements by start_year when end_date present
        for key in ("income", "balancesheet", "cashflow", "fina_indicator"):
            df = bundle[key]
            if not df.empty and "end_date" in df.columns:
                bundle[key] = df[df["end_date"] >= f"{start_year}0101"].reset_index(drop=True)
                results[key].provenance.rows = len(bundle[key])

        provenance = {k: v.provenance.to_dict() for k, v in results.items()}
        return bundle, provenance

    def core_gate(self, provenance: dict[str, Any]) -> tuple[bool, list[str]]:
        """Fail if any core cluster is source_failed or empty without genuine flag."""
        problems = []
        for name in CORE_CLUSTERS:
            p = provenance.get(name) or {}
            st = p.get("status")
            rows = int(p.get("rows") or 0)
            if st == SourceStatus.SOURCE_FAILED.value:
                problems.append(f"{name}: source_failed ({p.get('error')})")
            elif rows == 0 and st != SourceStatus.EMPTY_GENUINE.value:
                problems.append(f"{name}: zero rows status={st}")
            elif rows == 0 and st == SourceStatus.EMPTY_GENUINE.value:
                problems.append(f"{name}: empty_genuine (unexpected for core)")
        return (len(problems) == 0, problems)


def dt_years_since(start_year: int) -> int:
    import datetime as dt

    return max(1, dt.date.today().year - start_year + 1)


def save_bundle(
    bundle: dict[str, pd.DataFrame],
    out_dir: Path,
    provenance: dict[str, Any] | None = None,
) -> None:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = {}
    for name, df in bundle.items():
        path = out_dir / f"{name}.parquet"
        if df is None:
            df = pd.DataFrame()
        df.to_parquet(path, index=False)
        summary[name] = {"rows": int(len(df)), "cols": list(df.columns)[:40]}
    (out_dir / "_manifest.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if provenance is not None:
        (out_dir / "_provenance.json").write_text(
            json.dumps(provenance, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        # human-readable appendix seed
        lines = ["# data provenance (P0 multi-source)", ""]
        for k, p in provenance.items():
            lines.append(
                f"- **{k}**: status=`{p.get('status')}` used=`{p.get('used') or p.get('primary')}` "
                f"rows={p.get('rows')} {('— ' + p.get('note')) if p.get('note') else ''}"
            )
            if p.get("error"):
                lines.append(f"  - error: `{p['error']}`")
            for c in p.get("conflicts") or []:
                lines.append(f"  - conflict: {c}")
        (out_dir / "_provenance.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def resolve_ticker(code_or_name: str, name_hint: str | None = None) -> tuple[str, pd.DataFrame]:
    """P0: require parseable A-share code (name search deferred)."""
    code = normalize_a_code(code_or_name)
    basic = akf.fetch_stock_basic(code, name_hint=name_hint)
    return code, basic.df


def main() -> int:
    ap = argparse.ArgumentParser(description="A-share free multi-source collector (P0)")
    ap.add_argument("code", help="A-share code e.g. 600519.SH / 600519")
    ap.add_argument("--name", default="", help="company name hint")
    ap.add_argument("--start-year", type=int, default=2022)
    ap.add_argument("--out", default="", help="output raw_data dir")
    args = ap.parse_args()

    try:
        code = normalize_a_code(args.code)
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    out = Path(args.out) if args.out else config.output_dir(args.name or code.replace(".", "_")) / "raw_data"
    print(f"Collecting A-share bundle for {code} → {out}")
    c = AShareCollector()
    bundle, prov = c.collect_all(code, start_year=args.start_year)
    if args.name and not bundle["stock_basic"].empty:
        bundle["stock_basic"] = bundle["stock_basic"].copy()
        bundle["stock_basic"].loc[:, "name"] = args.name
    save_bundle(bundle, out, provenance=prov)
    ok, problems = c.core_gate(prov)
    print(json.dumps({"core_ok": ok, "problems": problems, "out": str(out)}, ensure_ascii=False, indent=2))
    # write gate beside provenance for Phase 1 agent
    (out / "_core_gate.json").write_text(
        json.dumps({"core_ok": ok, "problems": problems}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
