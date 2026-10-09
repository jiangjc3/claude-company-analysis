"""A-share collector facade — free multi-source, Tushare-shaped parquet bundle (P0+P1).

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
from .providers import eastmoney_flow as em_flow
from .providers import governance as gov
from .providers import sina_quote
from .providers.base import ClusterResult, SourceStatus


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

        daily = sina_quote.fetch_daily(code, years=max(3, dt_years_since(start_year)))
        results["daily"] = daily
        results["daily_basic"] = akf.fetch_daily_basic(code, daily.df if not daily.df.empty else None)

        results["anns"] = cninfo_prov.fetch_anns(code, days=90)

        # ---- P1 governance / calendar (C7–C16) ----
        results["top10_holders"] = gov.fetch_top10_holders(code)
        results["top10_floatholders"] = gov.fetch_top10_floatholders(code)
        results["stk_holdernumber"] = gov.fetch_stk_holdernumber(code)
        results["pledge_detail"] = gov.fetch_pledge_detail(code)
        results["stk_managers"] = gov.fetch_stk_managers(code)
        results["stk_rewards"] = gov.fetch_stk_rewards(code)
        results["repurchase"] = gov.fetch_repurchase(code)
        results["forecast_vip"] = gov.fetch_forecast_vip(code)
        results["express_vip"] = gov.fetch_express_vip(code)
        results["fina_mainbz"] = gov.fetch_fina_mainbz(code)
        results["dividend"] = gov.fetch_dividend(code)
        results["disclosure_date"] = gov.fetch_disclosure_date(code)
        results["share_float"] = gov.fetch_share_float(code)
        results["block_trade"] = gov.fetch_block_trade(code, days=90)

        # ---- P1 capital-flow raw tables also land in bundle (C18) ----
        results["moneyflow"] = em_flow.fetch_moneyflow(code, days=60)
        results["hk_hold"] = em_flow.fetch_hk_hold(code, days=90)
        results["margin_detail"] = em_flow.fetch_margin_detail(code, days=60)
        results["top_list"] = em_flow.fetch_top_list(code, days=30)
        results["top_inst"] = em_flow.fetch_top_inst(code, results["top_list"].df)
        results["moneyflow_hsgt"] = em_flow.fetch_moneyflow_hsgt(days=60)

        bundle = {k: v.df.copy() for k, v in results.items()}
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


def render_data_sources_md(provenance: dict[str, Any], *, title: str = "data_sources") -> str:
    """Machine-generated appendix seed from provenance (P1)."""
    lines = [
        f"# {title}",
        "",
        "空表语义: `ok` | `empty_genuine` | `source_failed` | `partial` | `deferred`",
        "",
        "| 簇 | status | used | rows | note |",
        "|---|---|---|---:|---|",
    ]
    gaps: list[str] = []
    for k, p in provenance.items():
        st = p.get("status")
        used = p.get("used") or p.get("primary") or ""
        note = (p.get("note") or "").replace("|", "/")
        err = p.get("error") or ""
        if err:
            note = f"{note} err=`{err[:80]}`".strip()
        lines.append(f"| `{k}` | `{st}` | `{used}` | {p.get('rows', 0)} | {note} |")
        if st in (SourceStatus.SOURCE_FAILED.value, SourceStatus.DEFERRED.value, SourceStatus.PARTIAL.value):
            gaps.append(f"- **{k}** (`{st}`): {p.get('note') or p.get('error') or 'see table'}")
        if st == SourceStatus.EMPTY_GENUINE.value and k in (
            "pledge_detail",
            "block_trade",
            "moneyflow",
            "top_list",
            "margin_detail",
            "hk_hold",
        ):
            gaps.append(
                f"- **{k}** (`empty_genuine`): source answered 0 rows — confirm vs 公告 before writing「无此事」"
            )
    if gaps:
        lines.extend(["", "## 缺口 / 降级 (不得静默当事实)", ""])
        lines.extend(gaps)
    for k, p in provenance.items():
        for c in p.get("conflicts") or []:
            lines.append(f"- conflict `{k}`: {c}")
    lines.append("")
    return "\n".join(lines)


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
        lines = ["# data provenance (P1 multi-source)", ""]
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
        (out_dir / "data_sources.md").write_text(
            render_data_sources_md(provenance), encoding="utf-8"
        )


def resolve_ticker(code_or_name: str, name_hint: str | None = None) -> tuple[str, pd.DataFrame]:
    """Require parseable A-share code (name search deferred)."""
    code = normalize_a_code(code_or_name)
    basic = akf.fetch_stock_basic(code, name_hint=name_hint)
    return code, basic.df


def sync_manifest_disclosure(company_dir: Path, raw_data_dir: Path) -> dict[str, Any]:
    """P2: push C14 nearest future date into company manifest (for --review / report stamp)."""
    from . import manifest as manifest_mod

    disc_path = Path(raw_data_dir) / "disclosure_date.parquet"
    picked, changed = manifest_mod.sync_disclosure_from_parquet(Path(company_dir), disc_path)
    return {
        "next_disclosure_date": picked,
        "manifest_updated": changed,
        "source": str(disc_path) if disc_path.exists() else None,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="A-share free multi-source collector (P0–P2)")
    ap.add_argument("code", help="A-share code e.g. 600519.SH / 600519")
    ap.add_argument("--name", default="", help="company name hint")
    ap.add_argument("--start-year", type=int, default=2022)
    ap.add_argument("--out", default="", help="output raw_data dir")
    ap.add_argument(
        "--company-dir",
        default="",
        help="optional output/{company}/ — sync next_disclosure_date into manifest.json (P2)",
    )
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
    ok_gate, problems = c.core_gate(prov)

    company_dir = Path(args.company_dir) if args.company_dir else out.parent
    disclosure_sync: dict[str, Any] = {}
    from . import manifest as manifest_mod

    if manifest_mod.load(company_dir) is not None:
        disclosure_sync = sync_manifest_disclosure(company_dir, out)
        print(
            f"disclosure sync: next={disclosure_sync.get('next_disclosure_date')} "
            f"updated={disclosure_sync.get('manifest_updated')}"
        )

    payload = {
        "core_ok": ok_gate,
        "problems": problems,
        "out": str(out),
        "disclosure": disclosure_sync,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    (out / "_core_gate.json").write_text(
        json.dumps({"core_ok": ok_gate, "problems": problems, "disclosure": disclosure_sync}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return 0 if ok_gate else 1


if __name__ == "__main__":
    sys.exit(main())
