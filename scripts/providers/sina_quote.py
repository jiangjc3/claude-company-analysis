"""Daily quotes via Sina (promoted from legacy_quote)."""
from __future__ import annotations

import datetime as dt

from .. import legacy_quote
from ..codes import normalize_a_code
from .base import ClusterResult, empty_genuine, failed, ok


def fetch_daily(ts_code: str, years: int = 3) -> ClusterResult:
    cluster = "daily"
    primary = "sina_kline"
    try:
        code = normalize_a_code(ts_code)
        datalen = max(years * 250, 250)
        df = legacy_quote.get_daily_history_legacy(code, datalen=datalen)
        if df.empty:
            return empty_genuine(cluster, primary, "sina returned no bars")
        end = dt.date.today()
        start = end - dt.timedelta(days=years * 365)
        df = legacy_quote.filter_by_date_range(
            df,
            start_date=start.strftime("%Y%m%d"),
            end_date=end.strftime("%Y%m%d"),
        )
        if df.empty:
            return empty_genuine(cluster, primary, "sina bars outside requested window")
        return ok(cluster, df, primary, note="amount may be close×volume estimate")
    except Exception as e:  # noqa: BLE001
        return failed(cluster, primary, e)
