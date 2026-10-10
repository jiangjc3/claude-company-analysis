"""Cursor Project orchestrator for A-share company-analysis (P0).

Machine phases (no LLM): check_env → init_run → a_share collect + derived
artifacts → (when nodes exist) assemble_report_v8 → lint_v8 → build_html.

LLM phases: emit filled prompts under runs/{date}/cursor_prompts/ for Cursor
workers that follow agents/*.md + references/*.md.

Usage (from repo root):
  python3 -m scripts.cursor_run collect --company 宁德时代 --ticker 300750.SZ
  python3 -m scripts.cursor_run import-pack --pack /path/to/pack --company 宁德时代
  python3 -m scripts.cursor_run emit-prompts --company 宁德时代
  python3 -m scripts.cursor_run assemble --company 宁德时代
  python3 -m scripts.cursor_run status --company 宁德时代
  python3 -m scripts.cursor_run resolve --query 宁德时代
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from . import config
from . import manifest as manifest_mod
from .codes import is_a_share_ticker, normalize_a_code

SKILL_ROOT = config.SKILL_ROOT
PYBIN = sys.executable

PHASE1_ARTIFACTS = (
    "data_snapshot.md",
    "audit_report.json",
    "red_flags.json",
    "peer_analysis.md",
    "capital_flow.md",
    "technical_analysis.md",
    "data_sources.md",
)
NODE_FILES = (
    "node-quality.md",
    "node-odds.md",
    "node-path.md",
    "node-state.md",
    "node-decision.md",
)


def _utf8() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass


def _run(args: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=str(cwd or SKILL_ROOT),
        text=True,
        capture_output=True,
        check=False,
    )


def _print_proc(proc: subprocess.CompletedProcess[str]) -> None:
    if proc.stdout:
        print(proc.stdout, end="" if proc.stdout.endswith("\n") else "\n")
    if proc.stderr:
        print(proc.stderr, end="" if proc.stderr.endswith("\n") else "\n", file=sys.stderr)


def company_dir(company: str) -> Path:
    return config.output_dir(company)


def latest_run_dir(base: Path) -> Path | None:
    m = manifest_mod.load(base)
    if not m or not m.get("runs"):
        return None
    date = m["runs"][-1]["date"]
    rd = base / "runs" / date
    return rd if rd.is_dir() else None


def resolve_query(query: str) -> dict[str, str]:
    """Resolve '宁德时代' / '300750' / '300750.SZ' → {company, ticker}."""
    q = (query or "").strip()
    if not q:
        raise ValueError("empty query")

    if is_a_share_ticker(q):
        ticker = normalize_a_code(q)
        name = ticker
        try:
            from .providers import akshare_fundamentals as akf

            basic = akf.fetch_stock_basic(ticker)
            if basic.df is not None and not basic.df.empty:
                name = str(basic.df.iloc[0].get("name") or ticker)
        except Exception:  # noqa: BLE001
            pass
        return {"company": name, "ticker": ticker}

    # Name → code via Eastmoney spot list
    import akshare as ak

    spot = ak.stock_zh_a_spot_em()
    col_code = "代码" if "代码" in spot.columns else spot.columns[1]
    col_name = "名称" if "名称" in spot.columns else spot.columns[2]
    hits = spot[spot[col_name].astype(str).str.contains(q, regex=False)]
    if hits.empty:
        # exact equality fallback
        hits = spot[spot[col_name].astype(str) == q]
    if hits.empty:
        raise ValueError(f"no A-share match for name {q!r}")
    if len(hits) > 1:
        # prefer exact name match
        exact = hits[hits[col_name].astype(str) == q]
        if not exact.empty:
            hits = exact
    row = hits.iloc[0]
    sym = str(row[col_code]).zfill(6)
    name = str(row[col_name])
    ticker = normalize_a_code(sym)
    if len(hits) > 1:
        print(
            f"⚠️  multiple name hits for {q!r}; using {name} ({ticker}). "
            f"Pass --ticker to override.",
            file=sys.stderr,
        )
    return {"company": name, "ticker": ticker}


def cmd_resolve(args: argparse.Namespace) -> int:
    try:
        info = resolve_query(args.query)
    except Exception as exc:  # noqa: BLE001
        print(f"❌ resolve failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(info, ensure_ascii=False, indent=2))
    return 0


def ensure_run(company: str, ticker: str, *, force_new: bool = False) -> tuple[Path, Path]:
    from . import init_run as init_run_mod

    base = company_dir(company)
    existing = latest_run_dir(base)
    if existing is not None and not force_new:
        # ensure ticker on manifest
        m = manifest_mod.load(base) or {}
        if ticker and not m.get("ticker"):
            m["ticker"] = ticker
            m["market"] = m.get("market") or "A股"
            manifest_mod.save(base, m)
        return base, existing

    base, run_dir = init_run_mod.init_run(company, ticker, run_type="full")
    if run_dir is None:
        raise RuntimeError("init_run did not produce run_dir")
    print(str(base))
    print(str(run_dir))
    return base, run_dir


def cmd_collect(args: argparse.Namespace) -> int:
    company = args.company
    ticker = args.ticker
    if not ticker and args.query:
        info = resolve_query(args.query)
        company = company or info["company"]
        ticker = info["ticker"]
    if not company or not ticker:
        # allow --company as query
        if company and not ticker:
            try:
                if is_a_share_ticker(company):
                    info = resolve_query(company)
                    company, ticker = info["company"], info["ticker"]
                else:
                    info = resolve_query(company)
                    company, ticker = info["company"], info["ticker"]
            except Exception as exc:  # noqa: BLE001
                print(f"❌ need --ticker or resolvable --company: {exc}", file=sys.stderr)
                return 2
        else:
            print("❌ --company and --ticker required (or --query)", file=sys.stderr)
            return 2

    ticker = normalize_a_code(ticker)

    proc = _run([PYBIN, "-m", "scripts.check_env"])
    _print_proc(proc)
    if proc.returncode != 0:
        return proc.returncode

    try:
        base, run_dir = ensure_run(company, ticker, force_new=args.new_run)
    except RuntimeError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 1

    print(f"→ artifacts_dir={base}")
    print(f"→ run_dir={run_dir}")

    steps: list[tuple[str, list[str]]] = [
        (
            "a_share_collector",
            [
                PYBIN,
                "-m",
                "scripts.a_share_collector",
                ticker,
                "--name",
                company,
                "--company-dir",
                str(base),
            ],
        ),
        (
            "financial_audit",
            [
                PYBIN,
                "-m",
                "scripts.financial_audit",
                str(base / "raw_data"),
                "--json",
                str(base / "audit_report.json"),
            ],
        ),
        (
            "derived_metrics",
            [PYBIN, "-m", "scripts.derived_metrics", str(base / "raw_data"), "--market", "a"],
        ),
        (
            "data_snapshot",
            [
                PYBIN,
                "-m",
                "scripts.data_snapshot",
                "--bundle",
                str(base / "raw_data"),
                "--out",
                str(base / "data_snapshot.md"),
                "--ts-code",
                ticker,
                "--company",
                company,
            ],
        ),
        (
            "red_flags",
            [
                PYBIN,
                "-m",
                "scripts.red_flags",
                "--audit-json",
                str(base / "audit_report.json"),
                "--out",
                str(base / "red_flags.json"),
            ],
        ),
        (
            "technical_analysis",
            [
                PYBIN,
                "-m",
                "scripts.technical_analysis",
                ticker,
                "--name",
                company,
                "--daily",
                str(base / "raw_data" / "daily.parquet"),
                "--out",
                str(base / "technical_analysis.md"),
            ],
        ),
        (
            "capital_flow",
            [
                PYBIN,
                "-m",
                "scripts.capital_flow",
                ticker,
                "--days",
                "60",
                "--out",
                str(base / "capital_flow.md"),
            ],
        ),
        (
            "peer_collector",
            [
                PYBIN,
                "-m",
                "scripts.peer_collector",
                ticker,
                "--peers",
                "5",
                "--name",
                company,
                "--out",
                str(base / "peer_analysis.md"),
            ],
        ),
    ]

    results: dict[str, Any] = {"company": company, "ticker": ticker, "steps": {}}
    fatal = False
    for name, cmd in steps:
        print(f"\n=== {name} ===")
        proc = _run(cmd)
        _print_proc(proc)
        ok = proc.returncode == 0
        results["steps"][name] = {"ok": ok, "exit": proc.returncode}
        if name == "a_share_collector" and not ok:
            fatal = True
            break
        # peer may fail (source_failed); non-fatal — status will show gap

    # Copy provenance helpers into company-level data_sources if collector wrote them
    prov_md = base / "raw_data" / "_provenance.md"
    if prov_md.exists():
        shutil.copy2(prov_md, base / "data_sources.md")
    elif not (base / "data_sources.md").exists():
        (base / "data_sources.md").write_text(
            f"# 数据来源与信息缺口\n\n{company} ({ticker}) — see raw_data/_provenance.*\n",
            encoding="utf-8",
        )

    # Minimal phase1-data / sentiment stubs so writers know machine layer done
    if not (base / "phase1-data.md").exists():
        (base / "phase1-data.md").write_text(
            f"# Phase 1 数据完成报告（机器层）\n\n"
            f"- company: {company}\n- ticker: {ticker}\n"
            f"- collector: a_share_collector via cursor_run\n"
            f"- **判定**: {'PASS' if not fatal else 'FAIL'}\n"
            f"- 舆情/PDF 精读留给 Cursor worker（doc-analyst / data-collector 补全）\n",
            encoding="utf-8",
        )
    if not (base / "sentiment.md").exists():
        (base / "sentiment.md").write_text(
            "# 舆情底稿\n\n（P0 机器层未拉舆情；Cursor worker 补 WebSearch 后改写本文件。）\n",
            encoding="utf-8",
        )

    status_path = run_dir / "cursor_machine_status.json"
    status_path.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"company_dir": str(base), "run_dir": str(run_dir), **results}, ensure_ascii=False, indent=2))
    return 1 if fatal else 0


def cmd_import_pack(args: argparse.Namespace) -> int:
    pack = Path(args.pack)
    company = args.company
    ticker = args.ticker or ""
    if not pack.is_dir():
        print(f"❌ pack not found: {pack}", file=sys.stderr)
        return 2

    if not ticker:
        # try manifest in pack
        for cand in (pack / "artifacts" / "manifest.json", pack / "manifest.json"):
            if cand.exists():
                meta = json.loads(cand.read_text(encoding="utf-8"))
                ticker = meta.get("ticker") or ticker
                company = company or meta.get("company") or company
                break
    if not company:
        print("❌ --company required", file=sys.stderr)
        return 2
    if not ticker:
        print("❌ --ticker required (not found in pack manifest)", file=sys.stderr)
        return 2
    ticker = normalize_a_code(ticker)

    try:
        base, run_dir = ensure_run(company, ticker, force_new=args.new_run)
    except RuntimeError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 1

    # Layout: pack may be {raw_data, artifacts} or flat company dir
    raw_src = pack / "raw_data" if (pack / "raw_data").is_dir() else None
    art_src = pack / "artifacts" if (pack / "artifacts").is_dir() else pack

    if raw_src:
        dest_raw = base / "raw_data"
        dest_raw.mkdir(parents=True, exist_ok=True)
        for p in raw_src.iterdir():
            target = dest_raw / p.name
            if p.is_dir():
                if target.exists():
                    shutil.rmtree(target)
                shutil.copytree(p, target)
            else:
                shutil.copy2(p, target)
        print(f"✅ raw_data ← {raw_src}")

    copied = []
    for name in (
        *PHASE1_ARTIFACTS,
        "audit_report.md",
        "metrics.json",
        "phase1-data.md",
        "sentiment.md",
        "phase2-documents.md",
        "_provenance.md",
        "_core_gate.json",
    ):
        src = art_src / name
        if src.is_file():
            shutil.copy2(src, base / name)
            copied.append(name)
    # Prefer pack provenance as data_sources
    if (art_src / "data_sources.md").is_file():
        shutil.copy2(art_src / "data_sources.md", base / "data_sources.md")
    elif (base / "_provenance.md").is_file() and not (base / "data_sources.md").is_file():
        shutil.copy2(base / "_provenance.md", base / "data_sources.md")

    if not (base / "phase1-data.md").exists():
        (base / "phase1-data.md").write_text(
            f"# Phase 1（import-pack）\n\n- company: {company}\n- ticker: {ticker}\n"
            f"- source: {pack}\n- **判定**: PASS\n",
            encoding="utf-8",
        )
    if not (base / "sentiment.md").exists():
        (base / "sentiment.md").write_text(
            "# 舆情底稿\n\n（import-pack：待 Cursor worker 补全）\n",
            encoding="utf-8",
        )

    # Sync market on manifest
    m = manifest_mod.load(base) or manifest_mod._new_manifest(company, ticker)  # noqa: SLF001
    m["company"] = company
    m["ticker"] = ticker
    m["market"] = "A股"
    manifest_mod.save(base, m)

    meta = {
        "company": company,
        "ticker": ticker,
        "company_dir": str(base),
        "run_dir": str(run_dir),
        "copied_artifacts": copied,
        "pack": str(pack),
    }
    (run_dir / "cursor_import.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    return 0


def _prompt_text(
    *,
    role: str,
    agent_file: str,
    company: str,
    ticker: str,
    date: str,
    run_dir: Path,
    artifacts_dir: Path,
    extra: str = "",
) -> str:
    art = str(artifacts_dir)
    rd = str(run_dir)
    return f"""# Cursor worker brief — {role}

You are running inside a **Cursor** Project (not Claude Code).
Follow the agent definition and manuals below. Write only your assigned artifacts.
Do **not** hand-edit other nodes' YAML. Do **not** paste raw DataFrame/stdout dumps.

## Identity
- role: {role}
- agent file: `{agent_file}`
- company: {company}
- ticker: {ticker}
- market: A股
- date: {date}
- PYBIN: `{PYBIN}`
- artifacts_dir: `{art}`
- run_dir: `{rd}`

## Protocol
1. Read `{agent_file}` plus the manuals it names (usually `references/judgment-chain.md` + your node manual).
2. Read evidence only from `artifacts_dir` (and PDFs under `raw_data/pdfs/` if present).
3. Write your output file(s) as specified by the agent doc.
4. Self-check with the gate command for your role (see below).
5. Reply with a short completion report only — include a line `**判定**: PASS` or `**判定**: 部分降级` or `**判定**: FAIL`.

## Gates (run from repo root)
- doc-analyst: `{PYBIN} -m scripts.check_phase2 --md {art}/phase2-documents.md`
- node writers: `{PYBIN} -m scripts.verdict_block --schema <node-*> --file {rd}/nodes/<file>.md`
- after all five nodes: coordinator runs `{PYBIN} -m scripts.cursor_run assemble --company {company}`

## Extra
{extra or "(none)"}
"""


def cmd_emit_prompts(args: argparse.Namespace) -> int:
    company = args.company
    base = company_dir(company)
    run_dir = latest_run_dir(base)
    if run_dir is None:
        print("❌ no run_dir — run collect or import-pack first", file=sys.stderr)
        return 2
    m = manifest_mod.load(base) or {}
    ticker = args.ticker or m.get("ticker") or ""
    date = run_dir.name
    out = run_dir / "cursor_prompts"
    out.mkdir(parents=True, exist_ok=True)

    specs = [
        (
            "01-data-collector-gaps.md",
            "data-collector (gaps)",
            "agents/data-collector.md",
            "Machine collect already done. Fill PDF download, sentiment.md, phase1-data.md gaps only. "
            "Do not re-fetch core financials unless core_ok is false.",
        ),
        (
            "02-doc-analyst.md",
            "doc-analyst",
            "agents/doc-analyst.md",
            "Write phase2-documents.md §1-§8. If PDFs missing, degrade explicitly — do not invent page cites.",
        ),
        (
            "03a-node-quality.md",
            "node-quality",
            "agents/node-quality.md",
            f"Write `{run_dir}/nodes/node-quality.md` (YAML verdict + body). Wave 1 — parallel with odds.",
        ),
        (
            "03b-node-odds.md",
            "node-odds",
            "agents/node-odds.md",
            f"Write `{run_dir}/nodes/node-odds.md`. Wave 1 — parallel with quality.",
        ),
        (
            "03c-node-path.md",
            "node-path",
            "agents/node-path.md",
            "Wave 2 — read odds YAML first. Include left_tail[].depth_pct.",
        ),
        (
            "03d-node-state.md",
            "node-state",
            "agents/node-state.md",
            "Wave 2 — read odds YAML first. Include critical_point.",
        ),
        (
            "03e-decision-writer.md",
            "decision-writer",
            "agents/decision-writer.md",
            "Wave 3 — read four node YAML blocks only. Include gear_cap + front_page_intro.",
        ),
        (
            "06a-reviewer-logic.md",
            "reviewer-logic",
            "agents/reviewer-logic.md",
            "After assemble+lint. Write reviewer response under run_dir/reviewer_responses/.",
        ),
        (
            "06b-reviewer-delivery.md",
            "reviewer-delivery",
            "agents/reviewer-delivery.md",
            "After assemble+lint. Parallel with logic reviewer.",
        ),
    ]

    written = []
    for fname, role, agent_file, extra in specs:
        text = _prompt_text(
            role=role,
            agent_file=agent_file,
            company=company,
            ticker=ticker,
            date=date,
            run_dir=run_dir,
            artifacts_dir=base,
            extra=extra,
        )
        path = out / fname
        path.write_text(text, encoding="utf-8")
        written.append(str(path))

    # Orchestrator checklist
    orch = out / "00-orchestrator.md"
    orch.write_text(
        f"""# Cursor orchestrator checklist — {company} ({ticker})

Repo root: `{SKILL_ROOT}`
artifacts_dir: `{base}`
run_dir: `{run_dir}`

## Order
1. (optional) `01-data-collector-gaps.md` if PDFs/sentiment missing
2. `02-doc-analyst.md` → gate `check_phase2`
3. Wave 1 parallel: `03a-node-quality.md` ∥ `03b-node-odds.md` → `verdict_block`
4. Wave 2 parallel: `03c-node-path.md` ∥ `03d-node-state.md` → `verdict_block`
5. Wave 3: `03e-decision-writer.md` → `verdict_block`
6. `python3 -m scripts.cursor_run assemble --company {company}`
7. Wave 6 parallel: `06a-reviewer-logic.md` ∥ `06b-reviewer-delivery.md` → `review_loop` / fresh-restart
8. Re-assemble + `build_html` if FIX applied

See also: `agents/cursor/orchestrator.md`, `CURSOR_RUN.md`.
""",
        encoding="utf-8",
    )
    written.insert(0, str(orch))

    print(json.dumps({"prompt_dir": str(out), "prompts": written}, ensure_ascii=False, indent=2))
    return 0


def cmd_assemble(args: argparse.Namespace) -> int:
    company = args.company
    base = company_dir(company)
    run_dir = latest_run_dir(base)
    if run_dir is None:
        print("❌ no run_dir", file=sys.stderr)
        return 2
    m = manifest_mod.load(base) or {}
    ticker = args.ticker or m.get("ticker") or ""
    date = run_dir.name
    nodes = run_dir / "nodes"
    missing = [n for n in NODE_FILES if not (nodes / n).is_file()]
    if missing:
        print(f"❌ missing nodes: {', '.join(missing)}", file=sys.stderr)
        print("→ run emit-prompts and Cursor writers first", file=sys.stderr)
        return 2

    proc = _run(
        [
            PYBIN,
            "-m",
            "scripts.assemble_report_v8",
            "--run-dir",
            str(run_dir),
            "--company",
            company,
            "--date",
            date,
            "--ticker",
            ticker,
            "--artifacts-dir",
            str(base),
        ]
    )
    _print_proc(proc)
    if proc.returncode != 0:
        return proc.returncode

    md_candidates = list(run_dir.glob(f"{company}-analysis-*.md"))
    md = md_candidates[0] if md_candidates else None

    proc = _run(
        [
            PYBIN,
            "-m",
            "scripts.lint_v8",
            "--run-dir",
            str(run_dir),
            "--artifacts-dir",
            str(base),
            *(["--md", str(md)] if md else []),
        ]
    )
    _print_proc(proc)
    lint_rc = proc.returncode
    if md:
        (run_dir / "lint_report.md").write_text(proc.stdout or "", encoding="utf-8")

    html_rc = 0
    if md:
        html_out = md.with_name("分析报告_dashboard.html")
        proc = _run(
            [
                PYBIN,
                "-m",
                "scripts.build_html",
                "--company",
                company,
                "--md",
                str(md),
                "--run-dir",
                str(run_dir),
                "--ticker",
                ticker,
                "--out",
                str(html_out),
                "--skip-lint",
            ]
        )
        _print_proc(proc)
        html_rc = proc.returncode

    summary = {
        "company": company,
        "ticker": ticker,
        "run_dir": str(run_dir),
        "md": str(md) if md else None,
        "lint_ok": lint_rc == 0,
        "html_ok": html_rc == 0,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if lint_rc == 0 and html_rc == 0 else 1


def cmd_status(args: argparse.Namespace) -> int:
    company = args.company
    base = company_dir(company)
    if not base.exists():
        print(json.dumps({"company": company, "exists": False}, ensure_ascii=False, indent=2))
        return 1
    m = manifest_mod.load(base)
    run_dir = latest_run_dir(base)
    phase1 = {name: (base / name).is_file() for name in PHASE1_ARTIFACTS}
    nodes = {}
    if run_dir:
        nodes = {name: (run_dir / "nodes" / name).is_file() for name in NODE_FILES}
    prompts = sorted(str(p.name) for p in (run_dir / "cursor_prompts").glob("*.md")) if run_dir else []
    md = list(run_dir.glob("*-analysis-*.md")) if run_dir else []
    html = list(run_dir.glob("*dashboard.html")) if run_dir else []
    core = None
    gate = base / "raw_data" / "_core_gate.json"
    if gate.exists():
        try:
            core = json.loads(gate.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            core = {"error": "invalid json"}

    payload = {
        "company": company,
        "company_dir": str(base),
        "manifest": m,
        "run_dir": str(run_dir) if run_dir else None,
        "core_gate": core,
        "phase1_artifacts": phase1,
        "phase1_ready": all(phase1.values()),
        "nodes": nodes,
        "nodes_ready": bool(nodes) and all(nodes.values()),
        "cursor_prompts": prompts,
        "report_md": [str(p) for p in md],
        "report_html": [str(p) for p in html],
        "next": (
            "assemble"
            if nodes and all(nodes.values()) and not md
            else (
                "emit-prompts + Cursor writers"
                if phase1 and all(phase1.get(k) for k in ("data_snapshot.md", "red_flags.json", "audit_report.json"))
                and not (nodes and all(nodes.values()))
                else "collect or import-pack"
            )
        ),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("resolve", help="Resolve company name or code → ticker")
    p.add_argument("--query", required=True)
    p.set_defaults(func=cmd_resolve)

    p = sub.add_parser("collect", help="Machine Phase 1 collect + derived artifacts")
    p.add_argument("--company", default="")
    p.add_argument("--ticker", default="")
    p.add_argument("--query", default="", help="name or code; fills company/ticker")
    p.add_argument("--new-run", action="store_true", help="force new runs/{date}/")
    p.set_defaults(func=cmd_collect)

    p = sub.add_parser("import-pack", help="Import existing raw_data/artifacts pack")
    p.add_argument("--pack", required=True)
    p.add_argument("--company", default="")
    p.add_argument("--ticker", default="")
    p.add_argument("--new-run", action="store_true")
    p.set_defaults(func=cmd_import_pack)

    p = sub.add_parser("emit-prompts", help="Write Cursor worker prompts into run_dir")
    p.add_argument("--company", required=True)
    p.add_argument("--ticker", default="")
    p.set_defaults(func=cmd_emit_prompts)

    p = sub.add_parser("assemble", help="assemble_report_v8 + lint_v8 + build_html")
    p.add_argument("--company", required=True)
    p.add_argument("--ticker", default="")
    p.set_defaults(func=cmd_assemble)

    p = sub.add_parser("status", help="Show pipeline readiness")
    p.add_argument("--company", required=True)
    p.set_defaults(func=cmd_status)

    return ap


def main(argv: list[str] | None = None) -> int:
    _utf8()
    ap = build_parser()
    args = ap.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
