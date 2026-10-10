"""Capital-flow cluster C18: moneyflow / 陆股通 / 两融 / 龙虎榜 (akshare / EM)."""
from __future__ import annotations

import datetime as dt

import pandas as pd

from ..codes import normalize_a_code, to_symbol6
from ..schema_bridge import bridge_top_inst_jgmmtj, bridge_top_inst_seats
from .base import ClusterResult, Provenance, SourceStatus, empty_genuine, failed, ok


def _ak():
    import akshare as ak

    return ak


def _market_of(ts_code: str) -> str:
    code = normalize_a_code(ts_code)
    suf = code.split(".")[1]
    return {"SH": "sh", "SZ": "sz", "BJ": "bj"}.get(suf, "sh")


def fetch_moneyflow(ts_code: str, days: int = 60) -> ClusterResult:
    """Individual fund flow → Tushare-ish moneyflow columns for capital_flow.py."""
    cluster, primary = "moneyflow", "akshare_stock_individual_fund_flow"
    code = normalize_a_code(ts_code)
    sym = to_symbol6(code)
    try:
        raw = _ak().stock_individual_fund_flow(stock=sym, market=_market_of(code))
        if raw is None or raw.empty:
            return empty_genuine(cluster, primary, "fund flow returned 0 rows")
        df = raw.copy()
        # Common EM columns (Chinese)
        rename = {}
        for c in df.columns:
            s = str(c)
            if s in ("日期", "date"):
                rename[c] = "trade_date"
            elif "超大单净流入" in s and "额" in s:
                rename[c] = "net_elg"
            elif "大单净流入" in s and "额" in s:
                rename[c] = "net_lg"
            elif "中单净流入" in s and "额" in s:
                rename[c] = "net_md"
            elif "小单净流入" in s and "额" in s:
                rename[c] = "net_sm"
            elif s.startswith("主力净流入") and "额" in s:
                rename[c] = "net_main"
        df = df.rename(columns=rename)
        if "trade_date" not in df.columns:
            return failed(cluster, primary, f"unexpected columns: {list(raw.columns)[:12]}")
        df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce").dt.strftime("%Y%m%d")
        df = df.dropna(subset=["trade_date"]).sort_values("trade_date")
        cutoff = (dt.date.today() - dt.timedelta(days=int(days * 1.5))).strftime("%Y%m%d")
        df = df[df["trade_date"] >= cutoff].copy()

        def _pos_neg(series: pd.Series) -> tuple[pd.Series, pd.Series]:
            s = pd.to_numeric(series, errors="coerce").fillna(0.0)
            # EM amounts often in 元; Tushare moneyflow uses 千元 — scale ÷1000
            s = s / 1000.0
            return s.clip(lower=0), (-s).clip(lower=0)

        for src, buy, sell in (
            ("net_elg", "buy_elg_amount", "sell_elg_amount"),
            ("net_lg", "buy_lg_amount", "sell_lg_amount"),
            ("net_md", "buy_md_amount", "sell_md_amount"),
            ("net_sm", "buy_sm_amount", "sell_sm_amount"),
        ):
            if src in df.columns:
                b, s = _pos_neg(df[src])
                df[buy] = b
                df[sell] = s
            else:
                df[buy] = 0.0
                df[sell] = 0.0
        # If only main net available, map into elg so derive still works
        if "net_main" in df.columns and df["buy_elg_amount"].sum() == 0 and df["buy_lg_amount"].sum() == 0:
            b, s = _pos_neg(df["net_main"])
            df["buy_elg_amount"] = b
            df["sell_elg_amount"] = s
        df["ts_code"] = code
        cols = [
            "ts_code",
            "trade_date",
            "buy_elg_amount",
            "sell_elg_amount",
            "buy_lg_amount",
            "sell_lg_amount",
            "buy_md_amount",
            "sell_md_amount",
            "buy_sm_amount",
            "sell_sm_amount",
        ]
        out = df[cols].reset_index(drop=True)
        if out.empty:
            return empty_genuine(cluster, primary, "no rows in window after filter")
        return ok(cluster, out, primary, note="EM net→buy/sell split; units≈千元 best-effort")
    except Exception as e:  # noqa: BLE001
        return failed(
            cluster,
            primary,
            e,
        )


def fetch_hk_hold(ts_code: str, days: int = 90) -> ClusterResult:
    cluster, primary = "hk_hold", "akshare_stock_hsgt_individual_em"
    code = normalize_a_code(ts_code)
    sym = to_symbol6(code)
    try:
        raw = _ak().stock_hsgt_individual_em(symbol=sym)
        if raw is None or raw.empty:
            return empty_genuine(cluster, primary, "no northbound hold history (may be ineligible)")
        df = raw.copy()
        ren = {}
        for c in df.columns:
            s = str(c)
            if "持股日期" in s or s == "日期":
                ren[c] = "trade_date"
            elif s == "持股数量":
                ren[c] = "hold_share"
            elif "占A股百分比" in s or "持股数量占" in s:
                ren[c] = "ratio"
        df = df.rename(columns=ren)
        if "trade_date" not in df.columns:
            return failed(cluster, primary, f"unexpected columns: {list(raw.columns)[:10]}")
        df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce").dt.strftime("%Y%m%d")
        df = df.dropna(subset=["trade_date"])
        cutoff = (dt.date.today() - dt.timedelta(days=int(days * 1.5))).strftime("%Y%m%d")
        df = df[df["trade_date"] >= cutoff].copy()
        df["ts_code"] = code
        if "ratio" not in df.columns:
            df["ratio"] = None
        # capital_flow._derive_metrics expects hold_ratio (Tushare name)
        df["hold_ratio"] = pd.to_numeric(df["ratio"], errors="coerce")
        if "hold_share" not in df.columns:
            df["hold_share"] = None
        out = df[["ts_code", "trade_date", "hold_share", "ratio", "hold_ratio"]].reset_index(drop=True)
        if out.empty:
            return empty_genuine(cluster, primary, "no hk_hold rows in window")
        return ok(cluster, out, primary)
    except Exception as e:  # noqa: BLE001
        return failed(cluster, primary, e)


def fetch_margin_detail(ts_code: str, days: int = 60) -> ClusterResult:
    """SSE/SZSE margin detail is date-scoped; sample recent open days and filter symbol."""
    cluster, primary = "margin_detail", "akshare_stock_margin_detail_exchange"
    code = normalize_a_code(ts_code)
    sym = to_symbol6(code)
    exch = code.split(".")[1]
    try:
        ak = _ak()
        # trade calendar
        try:
            cal = ak.tool_trade_date_hist_sina()
            dates = pd.to_datetime(cal["trade_date"], errors="coerce").dt.strftime("%Y%m%d")
            dates = [d for d in dates.dropna().tolist() if d <= dt.date.today().strftime("%Y%m%d")]
            dates = dates[-max(days, 20) :]
        except Exception:  # noqa: BLE001
            dates = [(dt.date.today() - dt.timedelta(days=i)).strftime("%Y%m%d") for i in range(days)]
            dates = list(reversed(dates))

        rows: list[pd.DataFrame] = []
        errors: list[str] = []
        # Cap network: every other day ~30 calls max
        sample = dates[::2][-30:]
        for d in sample:
            try:
                if exch == "SH":
                    raw = ak.stock_margin_detail_sse(date=d)
                    code_col = "标的证券代码" if raw is not None and "标的证券代码" in getattr(raw, "columns", []) else None
                    if code_col is None and raw is not None:
                        for c in raw.columns:
                            if "代码" in str(c):
                                code_col = c
                                break
                    rzye_col = next((c for c in (raw.columns if raw is not None else []) if "融资余额" in str(c)), None)
                else:
                    raw = ak.stock_margin_detail_szse(date=d)
                    code_col = next((c for c in (raw.columns if raw is not None else []) if "证券代码" in str(c) or c == "证券代码"), None)
                    if code_col is None and raw is not None:
                        for c in raw.columns:
                            if "代码" in str(c):
                                code_col = c
                                break
                    rzye_col = next((c for c in (raw.columns if raw is not None else []) if "融资余额" in str(c)), None)
                if raw is None or raw.empty or not code_col:
                    continue
                hit = raw[raw[code_col].astype(str).str.zfill(6) == sym]
                if hit.empty:
                    continue
                rzye = pd.to_numeric(hit.iloc[0][rzye_col], errors="coerce") if rzye_col else None
                rows.append(pd.DataFrame([{"ts_code": code, "trade_date": d, "rzye": rzye}]))
            except Exception as e:  # noqa: BLE001
                errors.append(f"{d}:{e}")
        if not rows:
            if errors and len(errors) >= 5:
                return failed(cluster, primary, "; ".join(errors[:3]))
            return empty_genuine(
                cluster,
                primary,
                "no margin rows (stock may not be marginable, or date sample missed) — not「无两融」",
            )
        out = pd.concat(rows, ignore_index=True).sort_values("trade_date")
        note = f"sampled {len(sample)} dates; hits={len(out)}; errors={len(errors)}"
        return ok(cluster, out, primary, note=note)
    except Exception as e:  # noqa: BLE001
        return failed(cluster, primary, e)


def fetch_top_list(ts_code: str, days: int = 30) -> ClusterResult:
    cluster, primary = "top_list", "akshare_stock_lhb_detail_em"
    code = normalize_a_code(ts_code)
    sym = to_symbol6(code)
    end = dt.date.today()
    start = end - dt.timedelta(days=days)
    try:
        raw = _ak().stock_lhb_detail_em(
            start_date=start.strftime("%Y%m%d"),
            end_date=end.strftime("%Y%m%d"),
        )
        if raw is None or raw.empty:
            return empty_genuine(cluster, primary, "no LHB rows in window (often genuine)")
        code_col = "代码" if "代码" in raw.columns else None
        if code_col is None:
            return failed(cluster, primary, f"unexpected columns: {list(raw.columns)[:10]}")
        hit = raw[raw[code_col].astype(str).str.zfill(6) == sym].copy()
        if hit.empty:
            return empty_genuine(cluster, primary, "stock not on LHB in window")
        ren = {}
        for c in hit.columns:
            s = str(c)
            if s == "上榜日":
                ren[c] = "trade_date"
            elif s == "上榜原因":
                ren[c] = "reason"
            elif s == "名称":
                ren[c] = "name"
            elif "龙虎榜净买额" == s:
                ren[c] = "net_amount"
        hit = hit.rename(columns=ren)
        hit["trade_date"] = pd.to_datetime(hit["trade_date"], errors="coerce").dt.strftime("%Y%m%d")
        hit["ts_code"] = code
        if "reason" not in hit.columns:
            hit["reason"] = ""
        cols = [c for c in ("ts_code", "trade_date", "name", "reason", "net_amount") if c in hit.columns]
        return ok(cluster, hit[cols].reset_index(drop=True), primary)
    except Exception as e:  # noqa: BLE001
        return failed(cluster, primary, e)


def fetch_top_inst(
    ts_code: str,
    top_list_df: pd.DataFrame | None = None,
    days: int = 30,
) -> ClusterResult:
    """龙虎榜机构席位 — seat-level (优先) + jgmmtj 机构合计 (备源).

    Sources (free, A-share):
    1. ``stock_lhb_stock_detail_em`` seats whose name contains「机构」(per trade_date)
    2. ``stock_lhb_jgmmtj_em`` filtered by SECURITY_CODE (aggregate buy/sell/net per day)
    """
    cluster = "top_inst"
    primary = "akshare_stock_lhb_stock_detail_em"
    secondary = "akshare_stock_lhb_jgmmtj_em"
    code = normalize_a_code(ts_code)
    sym = to_symbol6(code)
    end = dt.date.today()
    start = end - dt.timedelta(days=days)
    start_s, end_s = start.strftime("%Y%m%d"), end.strftime("%Y%m%d")
    errors: list[str] = []

    # ---- dates to expand seats ----
    dates: list[str] = []
    if top_list_df is not None and not top_list_df.empty and "trade_date" in top_list_df.columns:
        dates = (
            pd.to_datetime(top_list_df["trade_date"], errors="coerce")
            .dt.strftime("%Y%m%d")
            .dropna()
            .astype(str)
            .tolist()
        )
        dates = sorted({d for d in dates if start_s <= d <= end_s})
    if not dates:
        try:
            raw_dates = _ak().stock_lhb_stock_detail_date_em(symbol=sym)
            if raw_dates is not None and not raw_dates.empty:
                dcol = "交易日" if "交易日" in raw_dates.columns else raw_dates.columns[-1]
                dser = pd.to_datetime(raw_dates[dcol], errors="coerce").dt.strftime("%Y%m%d")
                dates = sorted({d for d in dser.dropna().astype(str).tolist() if start_s <= d <= end_s})
        except Exception as e:  # noqa: BLE001
            errors.append(f"detail_date:{e}")

    seat_frames: list[pd.DataFrame] = []
    for d in dates[:12]:  # cap network calls
        for flag in ("买入", "卖出"):
            try:
                raw = _ak().stock_lhb_stock_detail_em(symbol=sym, date=d, flag=flag)
                bridged = bridge_top_inst_seats(raw, code, d)
                if not bridged.empty:
                    seat_frames.append(bridged)
            except Exception as e:  # noqa: BLE001
                errors.append(f"seat:{d}:{flag}:{e}")

    if seat_frames:
        seats = pd.concat(seat_frames, ignore_index=True)
        # buy+sell pulls can duplicate the same 机构专用 row — keep one per date/exalter
        seats = seats.drop_duplicates(subset=["trade_date", "exalter", "buy", "sell", "net_buy"])
        return ok(
            cluster,
            seats.reset_index(drop=True),
            primary,
            secondary=secondary,
            note=f"seat-level 机构*; dates={len(dates)}; errors={len(errors)}",
        )

    # ---- fallback: market-wide jgmmtj filtered to this stock ----
    try:
        jg = _ak().stock_lhb_jgmmtj_em(start_date=start_s, end_date=end_s)
        if jg is not None and not jg.empty and "代码" in jg.columns:
            hit = jg[jg["代码"].astype(str).str.zfill(6) == sym].copy()
            bridged = bridge_top_inst_jgmmtj(hit, code)
            if not bridged.empty:
                return ok(
                    cluster,
                    bridged,
                    secondary,
                    secondary=primary,
                    note="jgmmtj aggregate 机构专用 per LHB day (seat names not expanded); "
                    f"seat_errors={len(errors)}",
                )
    except Exception as e:  # noqa: BLE001
        errors.append(f"jgmmtj:{e}")
        if len(errors) >= 3 and not dates:
            return failed(cluster, primary, "; ".join(errors[:3]), secondary=secondary)

    if errors and not dates and (top_list_df is None or top_list_df.empty):
        # No LHB activity and sources stumbled — still empty_genuine if jgmmtj answered 0
        pass
    return empty_genuine(
        cluster,
        primary,
        "no institution seat / jgmmtj rows in window "
        f"(top_list_dates={len(dates)}; errors={len(errors)}) — not「无机构」if sources failed",
    )


def fetch_moneyflow_hsgt(days: int = 60) -> ClusterResult:
    """Market-level northbound flow (background only)."""
    cluster, primary = "moneyflow_hsgt", "akshare_stock_hsgt_hist_em"
    try:
        # Prefer 北向资金 hist if available
        ak = _ak()
        raw = None
        for market in ("北向资金", "沪股通", "深股通"):
            try:
                raw = ak.stock_hsgt_hist_em(symbol=market)
                if raw is not None and not raw.empty:
                    break
            except Exception:  # noqa: BLE001
                continue
        if raw is None or raw.empty:
            return empty_genuine(cluster, primary, "hsgt hist unavailable")
        df = raw.copy()
        # keep a light frame
        date_col = next((c for c in df.columns if "日期" in str(c)), df.columns[0])
        df = df.rename(columns={date_col: "trade_date"})
        df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce").dt.strftime("%Y%m%d")
        cutoff = (dt.date.today() - dt.timedelta(days=int(days * 1.5))).strftime("%Y%m%d")
        df = df[df["trade_date"] >= cutoff].copy()
        if df.empty:
            return empty_genuine(cluster, primary, "no hsgt hist in window")
        return ok(cluster, df.reset_index(drop=True), primary, note="market-level northbound hist")
    except Exception as e:  # noqa: BLE001
        return failed(cluster, primary, e)


def fetch_trade_cal(n: int = 60) -> list[str]:
    """Recent n open dates YYYYMMDD newest-first."""
    try:
        cal = _ak().tool_trade_date_hist_sina()
        dates = pd.to_datetime(cal["trade_date"], errors="coerce").dt.strftime("%Y%m%d")
        today = dt.date.today().strftime("%Y%m%d")
        dates = [d for d in dates.dropna().tolist() if d <= today]
        return list(reversed(dates[-n:]))
    except Exception:  # noqa: BLE001
        today = dt.date.today()
        return [(today - dt.timedelta(days=i)).strftime("%Y%m%d") for i in range(n)]
