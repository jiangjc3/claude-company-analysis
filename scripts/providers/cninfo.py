"""Cninfo / notice list helpers (P0: akshare notice + optional direct search)."""
from __future__ import annotations

import datetime as dt

import pandas as pd

from ..codes import normalize_a_code, to_symbol6
from .base import ClusterResult, empty_genuine, failed, ok


def fetch_anns(ts_code: str, days: int = 90) -> ClusterResult:
    """Announcement titles for the last `days` — primary akshare individual notice."""
    cluster, primary = "anns", "akshare_stock_individual_notice_report"
    try:
        code = normalize_a_code(ts_code)
        sym = to_symbol6(code)
        import akshare as ak

        end = dt.date.today()
        start = end - dt.timedelta(days=days)
        # security: 代码；symbol: 类别
        raw = ak.stock_individual_notice_report(
            security=sym,
            symbol="全部",
            begin_date=start.strftime("%Y%m%d"),
            end_date=end.strftime("%Y%m%d"),
        )
        if raw is None or (isinstance(raw, pd.DataFrame) and raw.empty):
            return empty_genuine(cluster, primary, "no notices in window")
        df = raw.copy()
        # normalize columns best-effort
        colmap = {}
        for c in df.columns:
            cl = str(c).lower()
            if "日期" in str(c) or "date" in cl:
                colmap[c] = "ann_date"
            elif "标题" in str(c) or "title" in cl:
                colmap[c] = "title"
            elif "链接" in str(c) or "url" in cl or "http" in cl:
                colmap[c] = "url"
            elif "类型" in str(c) or "type" in cl:
                colmap[c] = "type"
        df = df.rename(columns=colmap)
        df["ts_code"] = code
        if "ann_date" in df.columns:
            df["ann_date"] = pd.to_datetime(df["ann_date"], errors="coerce").dt.strftime("%Y%m%d")
        return ok(cluster, df, primary, note="PDF URLs may need cninfo follow-up in Phase 1 agent")
    except Exception as e:  # noqa: BLE001
        return failed(cluster, primary, e)


def cninfo_search_hint(ts_code: str, company: str) -> str:
    """Hint string for WebSearch / manual PDF discovery (no network)."""
    code = normalize_a_code(ts_code)
    return f"site:cninfo.com.cn {code.split('.')[0]} {company} 年度报告 PDF"
