"""manifest — v8 契约层: runs/{date}/ 目录制 + 公司级状态唯一源 manifest.json。

每次分析 run 落在 output/{company}/runs/{YYYY-MM-DD}/ 独立目录(旧 run 整目录即留档);
manifest.json 挂在公司目录根, 是 runs 列表(full/incremental)、增量计数、上次全量日期、
下次预约披露日、所属对比组的唯一真相源(schema: scripts/schemas/manifest.schema.json)。

run 目录内固定子目录:
  nodes/           五个节点 md(顶部 YAML verdict 块, 见 verdict_block)
  assembly/        装配产物(首页/附录/metadata)
  reviewer_responses/  质量环往返

采集产物(raw_data/ / pdfs/ / data_snapshot.md …)落**公司级** `output/{company}/`, 跨 run 共享,
不在 run 目录内复制一份(= `{artifacts_dir}`, 见 references/phase-orchestration.md 目录结构约定)。

CLI(查状态 / 手工登记预约披露日; A 股由 a_share_collector / --sync-disclosure-from 自动写):
  python -m scripts.manifest --company-dir output/东山精密 --show
  python -m scripts.manifest --company-dir output/贵州茅台 --set-next-disclosure 2026-10-29
  python -m scripts.manifest --company-dir output/贵州茅台 \\
      --sync-disclosure-from output/贵州茅台/raw_data/disclosure_date.parquet
"""
from __future__ import annotations
import sys

import datetime as _dt
import json
from pathlib import Path

from . import verdict_block

MANIFEST_NAME = "manifest.json"
RUN_SUBDIRS = ("nodes", "assembly", "reviewer_responses")
RUN_TYPES = ("full", "incremental")


class RunExists(FileExistsError):
    """同日期 run 目录已存在(一天最多一个 run, 重跑先手动清理)。"""


def manifest_path(company_dir: Path) -> Path:
    return Path(company_dir) / MANIFEST_NAME


def load(company_dir: Path) -> dict | None:
    """读公司 manifest; 不存在返回 None。"""
    p = manifest_path(company_dir)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def save(company_dir: Path, data: dict) -> None:
    """校验后写 manifest(不合法直接抛错, 不落盘脏状态)。"""
    errs = verdict_block.validate(data, "manifest")
    if errs:
        raise ValueError(f"manifest 不合法, 拒绝写入: {errs}")
    manifest_path(company_dir).write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _new_manifest(company: str, ticker: str) -> dict:
    return {
        "company": company,
        "ticker": ticker,
        "market": None,
        "runs": [],
        "incremental_count": 0,
        "last_full_date": None,
        "next_disclosure_date": None,
        "compare_groups": [],
    }


def create_run(
    company_dir: Path,
    run_type: str,
    date: str | None = None,
    ticker: str = "",
) -> Path:
    """建 runs/{date}/ 目录树并把本次 run 记入 manifest, 返回 run 目录。

    full run 重置增量计数并更新 last_full_date; incremental 计数 +1。
    旧 run 目录不触碰(整目录留档)。
    """
    if run_type not in RUN_TYPES:
        raise ValueError(f"run_type 必须是 {'|'.join(RUN_TYPES)}, 收到: {run_type}")
    company_dir = Path(company_dir)
    date = date or _dt.date.today().isoformat()

    run_dir = company_dir / "runs" / date
    if run_dir.exists():
        raise RunExists(f"run 目录已存在: {run_dir}")
    for sub in RUN_SUBDIRS:
        (run_dir / sub).mkdir(parents=True)

    m = load(company_dir) or _new_manifest(company_dir.name, ticker)
    if ticker and not m.get("ticker"):
        m["ticker"] = ticker
    m["runs"].append({"date": date, "type": run_type})
    if run_type == "full":
        m["last_full_date"] = date
        m["incremental_count"] = 0
    else:
        m["incremental_count"] += 1
    save(company_dir, m)
    return run_dir


def latest_run(company_dir: Path) -> dict | None:
    """最近一次 run 的 {date, type}; 无 manifest 或无 run 返回 None。"""
    m = load(company_dir)
    if not m or not m["runs"]:
        return None
    return m["runs"][-1]


# ---------- 下次预约披露日(报告头部与主页卡片的「该什么时候回来看」)----------

# C14 disclosure_date 列名按修订优先级排(modify_date 覆盖 pre_ann_date / pre_date);
# schema_bridge 产出 pre_date / modify_date / actual_date; 旧 Tushare 形也认 pre_ann_date / ann_date。
# 列名不认识就返回 None —— 宁可留空, 不猜日期。
DISCLOSURE_DATE_COLUMNS = ("modify_date", "pre_ann_date", "pre_date", "ann_date")


def nearest_future_disclosure(
    records: list[dict], today: str | None = None
) -> str | None:
    """从 disclosure_date 记录里挑最近的未来预约披露日, 返回 YYYY-MM-DD。

    records = DataFrame.to_dict("records")(纯 dict 列表, 本函数不依赖 pandas)。
    """
    today = today or _dt.date.today().strftime("%Y%m%d")
    for col in DISCLOSURE_DATE_COLUMNS:
        future = sorted(
            str(r[col]) for r in records
            if r.get(col) and str(r[col]).isdigit() and len(str(r[col])) == 8
            and str(r[col]) > today
        )
        if future:
            raw = future[0]
            return f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"
    return None


def nearest_future_disclosure_from_df(df, today: str | None = None) -> str | None:
    """pandas DataFrame → nearest_future_disclosure(records)。空表 / 无可用列 → None。"""
    if df is None:
        return None
    try:
        empty = df.empty  # type: ignore[attr-defined]
    except Exception:
        return None
    if empty:
        return None
    records = df.to_dict("records")
    return nearest_future_disclosure(records, today=today)


def set_next_disclosure(company_dir: Path, date: str | None) -> bool:
    """把预约披露日写进 manifest; 无 manifest(还没 init_run)或日期为空则不动, 返回是否写了。"""
    m = load(company_dir)
    if m is None or not date:
        return False
    if m.get("next_disclosure_date") == date:
        return False
    m["next_disclosure_date"] = date
    save(company_dir, m)
    return True


def sync_disclosure_from_parquet(
    company_dir: Path, parquet_path: Path, today: str | None = None
) -> tuple[str | None, bool]:
    """从 C14 disclosure_date.parquet 同步 next_disclosure_date 到 manifest。

    返回 (picked_date | None, changed)。缺文件 / 空表 / 无未来日 → (None, False)。
    供 `--review` R1 与全量 Phase 1 在采集后门控调用(P2 硬化)。
    """
    path = Path(parquet_path)
    if not path.exists():
        return None, False
    try:
        import pandas as pd

        df = pd.read_parquet(path)
    except Exception:
        return None, False
    picked = nearest_future_disclosure_from_df(df, today=today)
    if not picked:
        return None, False
    return picked, set_next_disclosure(company_dir, picked)


# ---------- 对比组归属(票 10 --compare 的成员登记)----------

def add_compare_group(company_dir: Path, slug: str) -> bool:
    """把组 slug 记进这家的 manifest.compare_groups, 返回是否写了(已在组里就不动)。

    manifest 是公司级状态唯一源, 「我在哪些对比组里」也归它 —— `--review` 收尾靠这个字段
    知道该不该提示重装配对比页。没有 manifest(这家还没跑过 v8 分析)返回 False, 不建空壳。
    """
    m = load(company_dir)
    if m is None:
        return False
    groups = m.setdefault("compare_groups", [])
    if slug in groups:
        return False
    groups.append(slug)
    save(company_dir, m)
    return True


def remove_compare_group(company_dir: Path, slug: str) -> bool:
    """从 manifest.compare_groups 摘掉一个组(退组/删组时用), 返回是否写了。"""
    m = load(company_dir)
    if m is None or slug not in (m.get("compare_groups") or []):
        return False
    m["compare_groups"] = [g for g in m["compare_groups"] if g != slug]
    save(company_dir, m)
    return True


def main() -> int:
    for stream in (sys.stdout, sys.stderr):      # Windows 控制台 GBK 下 print emoji 会炸
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass

    import argparse

    ap = argparse.ArgumentParser(description="查看 / 更新公司 manifest.json")
    ap.add_argument("--company-dir", required=True, help="output/{company}/ 目录")
    ap.add_argument("--show", action="store_true", help="打印 manifest")
    ap.add_argument(
        "--set-next-disclosure",
        metavar="YYYY-MM-DD",
        help="手工登记下次预约披露日(通常不必; A 股用 --sync-disclosure-from)",
    )
    ap.add_argument(
        "--sync-disclosure-from",
        metavar="PARQUET",
        help="从 C14 disclosure_date.parquet 同步 next_disclosure_date(--review / Phase 1)",
    )
    args = ap.parse_args()

    company_dir = Path(args.company_dir)
    if load(company_dir) is None:
        print(f"❌ 没有 manifest: {manifest_path(company_dir)}(先跑 init_run --run-type full)")
        return 1
    if args.set_next_disclosure:
        changed = set_next_disclosure(company_dir, args.set_next_disclosure)
        print(("✅ 已登记" if changed else "· 未变化") + f" next_disclosure_date={args.set_next_disclosure}")
    if args.sync_disclosure_from:
        picked, changed = sync_disclosure_from_parquet(
            company_dir, Path(args.sync_disclosure_from)
        )
        if picked:
            print(
                ("✅ 已同步" if changed else "· 未变化")
                + f" next_disclosure_date={picked} ← {args.sync_disclosure_from}"
            )
        else:
            print(
                f"⚠️ 未从 {args.sync_disclosure_from} 解析到未来预约披露日"
                "（空表/源失败/无未来行 — 记入 data_sources 缺口,勿伪装成无披露）"
            )
    if args.show or not (args.set_next_disclosure or args.sync_disclosure_from):
        print(json.dumps(load(company_dir), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
