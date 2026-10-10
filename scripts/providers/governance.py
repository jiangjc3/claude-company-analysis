"""Governance / calendar clusters C7–C16 (free sources; Tushare-shaped outputs)."""
from __future__ import annotations

import datetime as dt
from typing import Callable

import pandas as pd

from ..codes import normalize_a_code, to_em_secid, to_symbol6
from ..schema_bridge import (
    bridge_block_trade,
    bridge_dividend,
    bridge_disclosure_date,
    bridge_express,
    bridge_forecast,
    bridge_holders,
    bridge_holdernumber,
    bridge_pledge,
    bridge_repurchase,
    bridge_share_float,
    bridge_stk_managers,
    bridge_stk_rewards,
)
from .base import ClusterResult, Provenance, SourceStatus, empty_genuine, failed, ok


def _ak():
    import akshare as ak

    return ak


def _ymd_series(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, errors="coerce").dt.strftime("%Y%m%d")


def _try(cluster: str, primary: str, fn: Callable[[], pd.DataFrame], bridge: Callable | None = None, note: str = "") -> ClusterResult:
    try:
        raw = fn()
        if raw is None or (isinstance(raw, pd.DataFrame) and raw.empty):
            return empty_genuine(cluster, primary, note or "source returned zero rows")
        df = bridge(raw) if bridge else raw
        if df is None or df.empty:
            return empty_genuine(cluster, primary, note or "bridge produced zero rows")
        return ok(cluster, df, primary, note=note)
    except Exception as e:  # noqa: BLE001
        return failed(cluster, primary, e)


# ---- C7 holders ----

def fetch_top10_holders(ts_code: str) -> ClusterResult:
    cluster, primary = "top10_holders", "akshare_stock_main_stock_holder"
    code = normalize_a_code(ts_code)
    sym = to_symbol6(code)

    def _fetch():
        return _ak().stock_main_stock_holder(stock=sym)

    def _bridge(raw: pd.DataFrame) -> pd.DataFrame:
        return bridge_holders(raw, code, float_mode=False)

    return _try(cluster, primary, _fetch, _bridge)


def fetch_top10_floatholders(ts_code: str) -> ClusterResult:
    cluster, primary = "top10_floatholders", "akshare_stock_circulate_stock_holder"
    code = normalize_a_code(ts_code)
    sym = to_symbol6(code)

    def _fetch():
        return _ak().stock_circulate_stock_holder(symbol=sym)

    def _bridge(raw: pd.DataFrame) -> pd.DataFrame:
        return bridge_holders(raw, code, float_mode=True)

    return _try(cluster, primary, _fetch, _bridge)


# ---- C8 holder number ----

def fetch_stk_holdernumber(ts_code: str) -> ClusterResult:
    cluster, primary = "stk_holdernumber", "akshare_stock_zh_a_gdhs_detail_em"
    code = normalize_a_code(ts_code)
    sym = to_symbol6(code)

    def _fetch():
        return _ak().stock_zh_a_gdhs_detail_em(symbol=sym)

    def _bridge(raw: pd.DataFrame) -> pd.DataFrame:
        return bridge_holdernumber(raw, code)

    return _try(cluster, primary, _fetch, _bridge)


# ---- C9 pledge ----

def fetch_pledge_detail(ts_code: str) -> ClusterResult:
    """Equity pledge detail. empty_genuine ≠ 'no pledge' only when source answered."""
    cluster, primary = "pledge_detail", "akshare_stock_gpzy_individual_pledge_ratio_detail_em"
    code = normalize_a_code(ts_code)
    sym = to_symbol6(code)

    def _fetch():
        return _ak().stock_gpzy_individual_pledge_ratio_detail_em(symbol=sym)

    def _bridge(raw: pd.DataFrame) -> pd.DataFrame:
        return bridge_pledge(raw, code)

    result = _try(
        cluster,
        primary,
        _fetch,
        _bridge,
        note="empty_genuine means source returned 0 rows — still confirm vs 年报/公告 before writing「无质押」",
    )
    if result.provenance.status == SourceStatus.SOURCE_FAILED:
        result.provenance.note = (
            "source_failed — do NOT interpret as「无质押」; treat as missing pledge data / red-flag gap"
        )
    return result


# ---- C10 managers / rewards ----

_EM_MGMT_URL = "https://emweb.securities.eastmoney.com/PC_HSF10/CompanyManagement/PageAjax"
_EM_MGMT_CACHE: dict[str, pd.DataFrame] = {}


def _fetch_em_company_management(ts_code: str) -> pd.DataFrame:
    """Eastmoney F10 公司高管列表 (`gglb`). Stable per-stock JSON; no Tushare."""
    import requests

    code = normalize_a_code(ts_code)
    if code in _EM_MGMT_CACHE:
        return _EM_MGMT_CACHE[code].copy()
    em = to_em_secid(code)
    r = requests.get(
        _EM_MGMT_URL,
        params={"code": em},
        timeout=30,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; claude-company-analysis; research)",
            "Referer": (
                "https://emweb.securities.eastmoney.com/PC_HSF10/"
                f"CompanyManagement/Index?type=web&code={em}"
            ),
        },
    )
    r.raise_for_status()
    data = r.json()
    rows = data.get("gglb") if isinstance(data, dict) else None
    df = pd.DataFrame(rows) if rows else pd.DataFrame()
    _EM_MGMT_CACHE[code] = df
    return df.copy()


def fetch_stk_managers(ts_code: str) -> ClusterResult:
    """董监高名单 — Eastmoney F10 CompanyManagement/PageAjax (per-stock)."""
    cluster, primary = "stk_managers", "eastmoney_f10_company_management"
    code = normalize_a_code(ts_code)
    try:
        raw = _fetch_em_company_management(code)
        if raw is None or raw.empty:
            return empty_genuine(
                cluster,
                primary,
                "F10 returned 0 manager rows — cross-check 年报「董监高」before writing「无高管」",
            )
        df = bridge_stk_managers(raw, code)
        if df.empty:
            return empty_genuine(cluster, primary, "bridge produced zero manager rows")
        return ok(
            cluster,
            df,
            primary,
            note="EM F10 gglb roster; resume/salary completeness varies — 年报 PDF still authoritative",
        )
    except Exception as e:  # noqa: BLE001
        return failed(cluster, primary, e)


def fetch_stk_rewards(ts_code: str) -> ClusterResult:
    """管理层薪酬/持股 — same F10 gglb SALARY/HOLD_NUM (元 / 股)."""
    cluster, primary = "stk_rewards", "eastmoney_f10_company_management"
    code = normalize_a_code(ts_code)
    try:
        raw = _fetch_em_company_management(code)
        if raw is None or raw.empty:
            return empty_genuine(
                cluster,
                primary,
                "F10 returned 0 rows — not the same as「无薪酬披露」; use 年报 PDF",
            )
        df = bridge_stk_rewards(raw, code)
        if df.empty:
            # Roster exists but every SALARY/HOLD_NUM null — common for some SOEs mid-year.
            return ClusterResult(
                name=cluster,
                df=df,
                provenance=Provenance(
                    cluster=cluster,
                    primary=primary,
                    used=primary,
                    status=SourceStatus.PARTIAL,
                    rows=0,
                    note="F10 roster present but SALARY/HOLD_NUM all null — Phase 2 年报「董监高薪酬」; "
                    "do not write「无薪酬披露」",
                ),
            )
        n_reward = int(df["reward"].notna().sum()) if "reward" in df.columns else 0
        n_hold = int(df["hold_vol"].notna().sum()) if "hold_vol" in df.columns else 0
        status = SourceStatus.OK if n_reward > 0 else SourceStatus.PARTIAL
        return ClusterResult(
            name=cluster,
            df=df,
            provenance=Provenance(
                cluster=cluster,
                primary=primary,
                used=primary,
                status=status,
                rows=len(df),
                note=f"reward_rows={n_reward}; hold_rows={n_hold}; units: reward≈元, hold_vol≈股",
            ),
        )
    except Exception as e:  # noqa: BLE001
        return failed(cluster, primary, e)


# ---- C11 repurchase ----

def fetch_repurchase(ts_code: str) -> ClusterResult:
    cluster, primary = "repurchase", "akshare_stock_repurchase_em"
    code = normalize_a_code(ts_code)
    sym = to_symbol6(code)

    def _fetch():
        df = _ak().stock_repurchase_em()
        if df is None or df.empty:
            return df
        col = "股票代码" if "股票代码" in df.columns else None
        if col is None:
            return df
        return df[df[col].astype(str).str.zfill(6) == sym].copy()

    def _bridge(raw: pd.DataFrame) -> pd.DataFrame:
        return bridge_repurchase(raw, code)

    return _try(cluster, primary, _fetch, _bridge)


# ---- C12 forecast / express ----

def _recent_report_ends(n: int = 6) -> list[str]:
    """Candidate report end dates YYYYMMDD for EM forecast/express market scrapes."""
    today = dt.date.today()
    ends = []
    y = today.year
    for year in range(y, y - 3, -1):
        for md in ("1231", "0930", "0630", "0331"):
            ends.append(f"{year}{md}")
    # only past / near ends
    cutoff = (today + dt.timedelta(days=45)).strftime("%Y%m%d")
    return [e for e in ends if e <= cutoff][:n]


def fetch_forecast_vip(ts_code: str) -> ClusterResult:
    cluster, primary = "forecast_vip", "akshare_stock_yjyg_em"
    code = normalize_a_code(ts_code)
    sym = to_symbol6(code)
    frames: list[pd.DataFrame] = []
    errors: list[str] = []
    for end in _recent_report_ends(8):
        try:
            raw = _ak().stock_yjyg_em(date=end)
            if raw is None or raw.empty or "股票代码" not in raw.columns:
                continue
            hit = raw[raw["股票代码"].astype(str).str.zfill(6) == sym].copy()
            if hit.empty:
                continue
            hit["_end_date"] = end
            frames.append(hit)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{end}:{e}")
    if not frames:
        if errors and len(errors) >= 3:
            return failed(cluster, primary, "; ".join(errors[:3]))
        return empty_genuine(
            cluster,
            primary,
            "no forecast rows for recent periods — not the same as「无预告」if source failed partially",
        )
    bridged = bridge_forecast(pd.concat(frames, ignore_index=True), code)
    note = f"scanned {len(_recent_report_ends(8))} periods; errors={len(errors)}"
    return ok(cluster, bridged, primary, note=note)


def fetch_express_vip(ts_code: str) -> ClusterResult:
    cluster, primary = "express_vip", "akshare_stock_yjkb_em"
    code = normalize_a_code(ts_code)
    sym = to_symbol6(code)
    frames: list[pd.DataFrame] = []
    errors: list[str] = []
    for end in _recent_report_ends(6):
        try:
            raw = _ak().stock_yjkb_em(date=end)
            if raw is None or raw.empty or "股票代码" not in raw.columns:
                continue
            hit = raw[raw["股票代码"].astype(str).str.zfill(6) == sym].copy()
            if hit.empty:
                continue
            hit["_end_date"] = end
            frames.append(hit)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{end}:{e}")
    if not frames:
        if errors and len(errors) >= 3:
            return failed(cluster, primary, "; ".join(errors[:3]))
        return empty_genuine(cluster, primary, "no express rows for recent periods")
    return ok(cluster, bridge_express(pd.concat(frames, ignore_index=True), code), primary)


# ---- C13 dividend ----

def fetch_dividend(ts_code: str) -> ClusterResult:
    cluster, primary = "dividend", "akshare_stock_dividend_cninfo"
    code = normalize_a_code(ts_code)
    sym = to_symbol6(code)

    def _fetch():
        return _ak().stock_dividend_cninfo(symbol=sym)

    def _bridge(raw: pd.DataFrame) -> pd.DataFrame:
        return bridge_dividend(raw, code)

    return _try(cluster, primary, _fetch, _bridge)


# ---- C14 disclosure calendar ----

def fetch_disclosure_date(ts_code: str) -> ClusterResult:
    cluster, primary = "disclosure_date", "akshare_stock_report_disclosure"
    code = normalize_a_code(ts_code)
    sym = to_symbol6(code)
    year = dt.date.today().year
    periods = [f"{year}年报", f"{year - 1}年报", f"{year}三季报", f"{year}半年报", f"{year}一季报"]
    frames: list[pd.DataFrame] = []
    errors: list[str] = []
    for period in periods:
        try:
            raw = _ak().stock_report_disclosure(market="沪深京", period=period)
            if raw is None or raw.empty or "股票代码" not in raw.columns:
                continue
            hit = raw[raw["股票代码"].astype(str).str.zfill(6) == sym].copy()
            if hit.empty:
                continue
            hit["_period"] = period
            frames.append(hit)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{period}:{e}")
    if not frames:
        if errors:
            return failed(cluster, primary, "; ".join(errors[:3]))
        return empty_genuine(cluster, primary, "no disclosure reservation rows")
    return ok(cluster, bridge_disclosure_date(pd.concat(frames, ignore_index=True), code), primary)


# ---- C15 share float ----

def fetch_share_float(ts_code: str, future_days: int = 365) -> ClusterResult:
    cluster, primary = "share_float", "akshare_stock_restricted_release_queue_sina"
    code = normalize_a_code(ts_code)
    sym = to_symbol6(code)

    def _fetch():
        return _ak().stock_restricted_release_queue_sina(symbol=sym)

    def _bridge(raw: pd.DataFrame) -> pd.DataFrame:
        df = bridge_share_float(raw, code)
        if df.empty or "float_date" not in df.columns:
            return df
        today = dt.date.today()
        end = today + dt.timedelta(days=future_days)
        # keep near-past 30d + future window (unlock calendar often includes history)
        start = (today - dt.timedelta(days=30)).strftime("%Y%m%d")
        end_s = end.strftime("%Y%m%d")
        mask = (df["float_date"] >= start) & (df["float_date"] <= end_s)
        filtered = df.loc[mask].copy()
        # If all historical, still return upcoming-empty as empty_genuine via caller
        return filtered

    result = _try(cluster, primary, _fetch, _bridge)
    if result.provenance.status == SourceStatus.OK and result.df.empty:
        return empty_genuine(
            cluster,
            primary,
            f"no unlocks in next {future_days}d (source had history only) — not a fetch failure",
        )
    return result


# ---- C16 block trade ----

def fetch_block_trade(ts_code: str, days: int = 90) -> ClusterResult:
    """Block trades — empty_genuine vs source_failed MUST stay distinct."""
    cluster, primary = "block_trade", "akshare_stock_dzjy_mrmx"
    code = normalize_a_code(ts_code)
    sym = to_symbol6(code)
    end = dt.date.today()
    start = end - dt.timedelta(days=days)

    def _fetch():
        raw = _ak().stock_dzjy_mrmx(
            symbol="A股",
            start_date=start.strftime("%Y%m%d"),
            end_date=end.strftime("%Y%m%d"),
        )
        if raw is None or raw.empty:
            return raw
        col = "证券代码" if "证券代码" in raw.columns else None
        if col is None:
            return raw
        return raw[raw[col].astype(str).str.zfill(6) == sym].copy()

    def _bridge(raw: pd.DataFrame) -> pd.DataFrame:
        return bridge_block_trade(raw, code)

    result = _try(
        cluster,
        primary,
        _fetch,
        _bridge,
        note="empty_genuine = source answered with 0 rows for this code/window; source_failed ≠ no block trades",
    )
    if result.provenance.status == SourceStatus.SOURCE_FAILED:
        result.provenance.note = (
            "source_failed — do NOT write「近 N 日无大宗交易」; check 减持公告 for trade method"
        )
    return result


# ---- C6 main business (best-effort text stub → structured if possible) ----

def fetch_fina_mainbz(ts_code: str) -> ClusterResult:
    cluster, primary = "fina_mainbz", "akshare_stock_zyjs_ths"
    code = normalize_a_code(ts_code)
    sym = to_symbol6(code)

    def _fetch():
        return _ak().stock_zyjs_ths(symbol=sym)

    def _bridge(raw: pd.DataFrame) -> pd.DataFrame:
        if raw is None or raw.empty:
            return pd.DataFrame()
        # THS returns business description — not a multi-row segment table.
        # Keep a single-row placeholder so snapshot sees something without faking segments.
        row = raw.iloc[0]
        return pd.DataFrame(
            [
                {
                    "ts_code": code,
                    "end_date": "",
                    "bz_item": str(row.get("产品名称") or row.get("主营业务") or "")[:200],
                    "bz_sales": None,
                    "bz_profit": None,
                    "bz_cost": None,
                    "curr_type": "CNY",
                    "bz_type": "P",
                }
            ]
        )

    result = _try(
        cluster,
        primary,
        _fetch,
        _bridge,
        note="THS 主营 is descriptive text, not audited segment table — Phase 2 PDF 附注 is authoritative",
    )
    if result.provenance.status == SourceStatus.OK:
        result.provenance.status = SourceStatus.PARTIAL
    return result
