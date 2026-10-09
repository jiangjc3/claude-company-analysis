"""AkShare / Eastmoney fundamentals for A-shares (P0 core clusters)."""
from __future__ import annotations

import datetime as dt

import pandas as pd

from ..codes import normalize_a_code, to_em_secid, to_symbol6
from ..schema_bridge import (
    CRITICAL_BALANCE,
    CRITICAL_CASHFLOW,
    CRITICAL_INCOME,
    bridge_balancesheet,
    bridge_cashflow,
    bridge_income,
    bridge_indicator_ths,
    missing_critical,
)
from .base import ClusterResult, SourceStatus, empty_genuine, failed, ok


def _ak():
    import akshare as ak  # deferred — check_env validates presence

    return ak


def fetch_stock_basic(ts_code: str, name_hint: str | None = None) -> ClusterResult:
    cluster, primary = "stock_basic", "akshare_spot_em"
    try:
        code = normalize_a_code(ts_code)
        sym = to_symbol6(code)
        ak = _ak()
        # spot list is heavy; try individual hist meta via profit sheet header first
        name = name_hint or ""
        industry = ""
        try:
            spot = ak.stock_zh_a_spot_em()
            row = spot[spot["代码"].astype(str).str.zfill(6) == sym]
            if not row.empty:
                name = name or str(row.iloc[0].get("名称", "") or "")
        except Exception:  # noqa: BLE001
            primary = "akshare_spot_em+manual"
        exch = code.split(".")[1]
        market = {"SH": "主板" if not sym.startswith("688") else "科创板", "SZ": "创业板" if sym.startswith("3") else "主板", "BJ": "北交所"}.get(exch, "")
        df = pd.DataFrame(
            [
                {
                    "ts_code": code,
                    "symbol": sym,
                    "name": name or sym,
                    "area": "",
                    "industry": industry,
                    "market": market,
                    "exchange": exch,
                    "list_status": "L",
                    "list_date": "",
                }
            ]
        )
        return ok(cluster, df, primary, note="industry often empty in P0 — peer should use --peer-codes")
    except Exception as e:  # noqa: BLE001
        return failed(cluster, primary, e)


def fetch_income(ts_code: str) -> ClusterResult:
    return _fetch_statement(ts_code, "income", "stock_profit_sheet_by_report_em", bridge_income, CRITICAL_INCOME)


def fetch_balancesheet(ts_code: str) -> ClusterResult:
    return _fetch_statement(
        ts_code, "balancesheet", "stock_balance_sheet_by_report_em", bridge_balancesheet, CRITICAL_BALANCE
    )


def fetch_cashflow(ts_code: str) -> ClusterResult:
    return _fetch_statement(
        ts_code, "cashflow", "stock_cash_flow_sheet_by_report_em", bridge_cashflow, CRITICAL_CASHFLOW
    )


def _fetch_statement(ts_code, cluster, api_name, bridge_fn, critical) -> ClusterResult:
    primary = f"akshare_{api_name}"
    try:
        code = normalize_a_code(ts_code)
        ak = _ak()
        fn = getattr(ak, api_name)
        raw = fn(symbol=to_em_secid(code))
        if raw is None or raw.empty:
            return empty_genuine(cluster, primary)
        df = bridge_fn(raw)
        miss = missing_critical(df, critical)
        note = ""
        if miss:
            note = f"missing critical columns after bridge: {', '.join(miss)}"
        status_ok = ok(cluster, df, primary, note=note)
        if miss:
            status_ok.provenance.status = SourceStatus.PARTIAL
        return status_ok
    except Exception as e:  # noqa: BLE001
        return failed(cluster, primary, e)


def fetch_fina_indicator(ts_code: str) -> ClusterResult:
    cluster, primary = "fina_indicator", "akshare_financial_analysis_indicator"
    try:
        code = normalize_a_code(ts_code)
        ak = _ak()
        raw = ak.stock_financial_analysis_indicator(symbol=to_symbol6(code))
        if raw is None or raw.empty:
            return empty_genuine(cluster, primary)
        df = bridge_indicator_ths(raw)
        df["ts_code"] = code
        return ok(cluster, df, primary)
    except Exception as e:  # noqa: BLE001
        return failed(cluster, primary, e)


def fetch_daily_basic(ts_code: str, daily: pd.DataFrame | None = None) -> ClusterResult:
    """Best-effort valuation snapshot from spot + last close (P0)."""
    cluster, primary = "daily_basic", "akshare_spot_em"
    try:
        code = normalize_a_code(ts_code)
        sym = to_symbol6(code)
        ak = _ak()
        pe = pb = total_mv = circ_mv = turnover = None
        close = None
        try:
            spot = ak.stock_zh_a_spot_em()
            row = spot[spot["代码"].astype(str).str.zfill(6) == sym]
            if not row.empty:
                r = row.iloc[0]
                close = r.get("最新价")
                pe = r.get("市盈率-动态")
                pb = r.get("市净率")
                total_mv = r.get("总市值")
                circ_mv = r.get("流通市值")
                turnover = r.get("换手率")
        except Exception as e:  # noqa: BLE001
            primary = "daily_derive"
            if daily is None or daily.empty:
                return failed(cluster, "akshare_spot_em", e)
        if close is None and daily is not None and not daily.empty:
            close = daily.sort_values("trade_date").iloc[-1]["close"]
            primary = "sina_daily_derive"
        trade_date = dt.date.today().strftime("%Y%m%d")
        if daily is not None and not daily.empty:
            trade_date = str(daily.sort_values("trade_date").iloc[-1]["trade_date"])
        # Eastmoney spot 总市值常为元
        def _yi(x):
            if x is None or (isinstance(x, float) and pd.isna(x)):
                return None
            try:
                v = float(x)
            except (TypeError, ValueError):
                return None
            return v / 1e8 if v > 1e6 else v

        df = pd.DataFrame(
            [
                {
                    "ts_code": code,
                    "trade_date": trade_date,
                    "close": close,
                    "pe": pe,
                    "pe_ttm": pe,
                    "pb": pb,
                    "total_mv": _yi(total_mv) * 10000 if _yi(total_mv) is not None else None,  # 万元兼容 tushare
                    "circ_mv": _yi(circ_mv) * 10000 if _yi(circ_mv) is not None else None,
                    "turnover_rate": turnover,
                }
            ]
        )
        return ok(cluster, df, primary, note="units best-effort; verify against exchange if used for sizing")
    except Exception as e:  # noqa: BLE001
        return failed(cluster, primary, e)
