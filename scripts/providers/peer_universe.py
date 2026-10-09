"""Peer universe C20 — free industry constituents + optional --peer-codes."""
from __future__ import annotations

import datetime as dt
from typing import Any

import pandas as pd

from ..codes import normalize_a_code, to_symbol6
from .base import ClusterResult, SourceStatus, empty_genuine, failed, ok


def _ak():
    import akshare as ak

    return ak


def _row_from_daily_basic(ts_code: str, name_hint: str = "") -> dict[str, Any] | None:
    """Fallback single-name row when full spot list is blocked.

    Always returns a row for a valid code (valuation fields may be null if EM spot
    is rate-limited); callers should tolerate missing total_mv on manual peers.
    """
    from . import akshare_fundamentals as akf
    from . import sina_quote

    code = normalize_a_code(ts_code)
    basic = akf.fetch_stock_basic(code, name_hint=name_hint or None)
    daily_basic = akf.fetch_daily_basic(code)
    name = name_hint or code
    if not basic.df.empty:
        name = str(basic.df.iloc[0].get("name") or name)
    pe = pb = close = total_mv = None
    if not daily_basic.df.empty:
        r = daily_basic.df.iloc[0]
        pe = r.get("pe_ttm")
        pb = r.get("pb")
        close = r.get("close")
        total_mv = r.get("total_mv")  # already 万元-ish from P0 bridge
    if close is None:
        try:
            daily = sina_quote.fetch_daily(code, years=1)
            if not daily.df.empty:
                close = daily.df.sort_values("trade_date").iloc[-1]["close"]
        except Exception:  # noqa: BLE001
            pass
    # Placeholder mv so manual peer sort still works when spot valuation is down
    if total_mv is None and close is not None:
        total_mv = float(close)  # not real 万元市值 — flagged in note by caller
    return {
        "ts_code": code,
        "symbol": to_symbol6(code),
        "name": name,
        "industry": "",
        "list_date": "",
        "market": code.split(".")[1],
        "total_mv": total_mv,
        "pe_ttm": pe,
        "pb": pb,
        "close": close,
        "_mv_is_placeholder": total_mv is not None and pe is None and pb is None,
    }

def fetch_stock_universe(peer_codes: list[str] | None = None, target_code: str | None = None) -> ClusterResult:
    """A-share universe scaffold.

    Prefer full spot list for auto industry peers. When `peer_codes` is given (or spot
    fails), fall back to per-code daily_basic rows so `--peer-codes` stays usable.
    """
    cluster, primary = "peer_universe", "akshare_stock_zh_a_spot_em"
    # Manual path: never require the heavy spot scrape
    if peer_codes is not None and target_code:
        rows = []
        missing = []
        for c in [target_code, *peer_codes]:
            try:
                row = _row_from_daily_basic(c)
            except Exception as e:  # noqa: BLE001
                missing.append(f"{c}:{e}")
                row = None
            if row is None:
                missing.append(str(c))
            else:
                rows.append(row)
        if not rows:
            return failed(cluster, "akshare_daily_basic_per_code", "manual peer rows all empty")
        df = pd.DataFrame(rows).drop_duplicates(subset=["ts_code"])
        note = "manual --peer-codes via per-code daily_basic/sina"
        if missing:
            note += f"; missing={missing}"
        if df.get("_mv_is_placeholder") is not None and df["_mv_is_placeholder"].any():
            note += "; total_mv placeholder (spot valuation unavailable) — PE/PB may be blank"
            # drop helper col before return
        if "_mv_is_placeholder" in df.columns:
            df = df.drop(columns=["_mv_is_placeholder"])
        status_ok = ok(cluster, df, "akshare_daily_basic_per_code", note=note)
        if "placeholder" in note:
            from .base import SourceStatus

            status_ok.provenance.status = SourceStatus.PARTIAL
        return status_ok
    try:
        spot = _ak().stock_zh_a_spot_em()
        if spot is None or spot.empty:
            return empty_genuine(cluster, primary, "spot list empty")
        df = spot.copy()
        df["symbol"] = df["代码"].astype(str).str.zfill(6)

        def _ts(sym: str) -> str:
            try:
                return normalize_a_code(sym)
            except ValueError:
                return ""

        df["ts_code"] = df["symbol"].map(_ts)
        df = df[df["ts_code"] != ""].copy()
        df["name"] = df["名称"].astype(str)
        mv = pd.to_numeric(df.get("总市值"), errors="coerce")
        df["total_mv"] = mv / 1e4  # → 万元
        df["pe_ttm"] = pd.to_numeric(df.get("市盈率-动态"), errors="coerce")
        df["pb"] = pd.to_numeric(df.get("市净率"), errors="coerce")
        df["close"] = pd.to_numeric(df.get("最新价"), errors="coerce")
        df["industry"] = ""
        df["list_date"] = ""
        df["market"] = df["ts_code"].str.split(".").str[1]
        out = df[
            ["ts_code", "symbol", "name", "industry", "list_date", "market", "total_mv", "pe_ttm", "pb", "close"]
        ].reset_index(drop=True)
        return ok(cluster, out, primary, note="industry blank until board enrich; prefer --peer-codes")
    except Exception as e:  # noqa: BLE001
        # If caller intended auto mode but spot died, surface failure (collect_peers may retry manual).
        return failed(cluster, primary, e)

def enrich_industry_from_board(universe: pd.DataFrame, target_code: str) -> tuple[pd.DataFrame, str]:
    """Try to set industry via Eastmoney industry board containing the target.

    Returns (universe_with_industry, industry_name). On failure industry stays blank.
    """
    if universe is None or universe.empty:
        return universe, ""
    code = normalize_a_code(target_code)
    sym = to_symbol6(code)
    try:
        ak = _ak()
        boards = ak.stock_board_industry_name_em()
        if boards is None or boards.empty:
            return universe, ""
        name_col = "板块名称" if "板块名称" in boards.columns else boards.columns[0]
        # Cap: scan up to ~40 boards (rate-limit friendly) prioritizing larger ones if 排名 exists
        names = boards[name_col].astype(str).tolist()[:40]
        for bname in names:
            try:
                cons = ak.stock_board_industry_cons_em(symbol=bname)
            except Exception:  # noqa: BLE001
                continue
            if cons is None or cons.empty:
                continue
            ccol = "代码" if "代码" in cons.columns else None
            if ccol is None:
                continue
            if (cons[ccol].astype(str).str.zfill(6) == sym).any():
                # mark all constituents with this industry
                out = universe.copy()
                cons_syms = set(cons[ccol].astype(str).str.zfill(6).tolist())
                mask = out["symbol"].isin(cons_syms)
                out.loc[mask, "industry"] = bname
                out.loc[out["ts_code"] == code, "industry"] = bname
                return out, bname
        return universe, ""
    except Exception:  # noqa: BLE001
        return universe, ""


def build_peer_pool(
    universe: pd.DataFrame,
    target_code: str,
    industry: str,
    peer_codes: list[str] | None = None,
) -> tuple[pd.DataFrame, bool, list[str], dict[str, Any]]:
    """Return (pool, manual, missing, provenance_meta)."""
    code = normalize_a_code(target_code)
    meta: dict[str, Any] = {"status": SourceStatus.OK.value, "note": ""}
    if peer_codes:
        wanted = set()
        for c in peer_codes:
            try:
                wanted.add(normalize_a_code(c))
            except ValueError:
                continue
        wanted.add(code)
        pool = universe[universe["ts_code"].isin(wanted)].copy()
        missing = sorted(wanted - set(pool["ts_code"].astype(str)))
        meta["note"] = "manual --peer-codes"
        return pool, True, missing, meta
    if not industry:
        meta["status"] = SourceStatus.PARTIAL.value
        meta["note"] = (
            "industry unknown after free-source enrich — auto peer disabled; "
            "use --peer-codes. Do not invent peers."
        )
        # still return target-only so caller can degrade cleanly
        pool = universe[universe["ts_code"] == code].copy()
        return pool, False, [], meta
    pool = universe[universe["industry"] == industry].copy()
    if len(pool) < 2:
        meta["status"] = SourceStatus.PARTIAL.value
        meta["note"] = f"industry '{industry}' has <2 names in enriched universe"
    return pool, False, [], meta


def latest_trade_date_str() -> str:
    return dt.date.today().strftime("%Y%m%d")
