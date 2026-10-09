"""Map free-source columns → legacy Tushare-shaped columns for downstream scripts."""
from __future__ import annotations

from typing import Iterable

import pandas as pd

# Eastmoney (akshare *_by_report_em) → tushare income core
INCOME_EM_TO_TS: dict[str, str] = {
    "SECUCODE": "ts_code",
    "NOTICE_DATE": "ann_date",
    "UPDATE_DATE": "f_ann_date",
    "REPORT_DATE": "end_date",
    "REPORT_TYPE": "report_type_name",
    "TOTAL_OPERATE_INCOME": "total_revenue",
    "OPERATE_INCOME": "revenue",
    "OPERATE_COST": "oper_cost",
    "OPERATE_TAX_ADD": "biz_tax_surchg",
    "SALE_EXPENSE": "sell_exp",
    "MANAGE_EXPENSE": "admin_exp",
    "FINANCE_EXPENSE": "fin_exp",
    "RESEARCH_EXPENSE": "rd_exp",
    "ASSET_IMPAIRMENT_INCOME": "assets_impair_loss",
    "FAIRVALUE_CHANGE_INCOME": "fv_value_chg_gain",
    "INVEST_INCOME": "invest_income",
    "INVEST_JOINT_INCOME": "ass_invest_income",
    "EXCHANGE_INCOME": "forex_gain",
    "OPERATE_PROFIT": "operate_profit",
    "NONBUSINESS_INCOME": "non_oper_income",
    "NONBUSINESS_EXPENSE": "non_oper_exp",
    "TOTAL_PROFIT": "total_profit",
    "INCOME_TAX": "income_tax",
    "NETPROFIT": "n_income",
    "PARENT_NETPROFIT": "n_income_attr_p",
    "MINORITY_INTEREST": "minority_gain",
    "BASIC_EPS": "basic_eps",
    "DILUTED_EPS": "diluted_eps",
}

BALANCE_EM_TO_TS: dict[str, str] = {
    "SECUCODE": "ts_code",
    "NOTICE_DATE": "ann_date",
    "UPDATE_DATE": "f_ann_date",
    "REPORT_DATE": "end_date",
    "REPORT_TYPE": "report_type_name",
    "SHARE_CAPITAL": "total_share",
    "MONETARYFUNDS": "money_cap",
    "ACCOUNTS_RECE": "accounts_receiv",
    "PREPAYMENT": "prepayment",
    "INVENTORY": "inventories",
    "OTHER_CURRENT_ASSET": "oth_cur_assets",
    "TOTAL_CURRENT_ASSETS": "total_cur_assets",
    "LONG_EQUITY_INVEST": "lt_eqt_invest",
    "FIXED_ASSET": "fix_assets",
    "CIP": "cip",
    "INTANGIBLE_ASSET": "intan_assets",
    "GOODWILL": "goodwill",
    "DEFER_TAX_ASSET": "defer_tax_assets",
    "TOTAL_NONCURRENT_ASSETS": "total_nca",
    "TOTAL_ASSETS": "total_assets",
    "SHORT_LOAN": "st_borr",
    "NOTE_PAYABLE": "notes_payable",
    "ACCOUNTS_PAYABLE": "acct_payable",
    "ADVANCE_RECEIVABLES": "adv_receipts",
    "CONTRACT_LIAB": "contract_liab",
    "CONTRACT_ASSET": "contract_assets",
    "DEFER_INCOME": "deferred_inc",
    "DEFER_INCOME_NONCURRENT": "defer_inc_non_cur_liab",
    "NONCURRENT_DEFER_INCOME": "defer_inc_non_cur_liab",
    "STAFF_SALARY": "payroll_payable",
    "TAX_PAYABLE": "taxes_payable",
    "OTHER_PAYABLE": "oth_payable",
    "NONCURRENT_LIAB_1YEAR": "non_cur_liab_due_1y",
    "TOTAL_CURRENT_LIAB": "total_cur_liab",
    "LONG_LOAN": "lt_borr",
    "BOND_PAYABLE": "bond_payable",
    "LONG_PAYABLE": "lt_payable",
    "DEFER_TAX_LIAB": "defer_tax_liab",
    "TOTAL_NONCURRENT_LIAB": "total_ncl",
    "OTHER_CURRENT_LIAB": "oth_cur_liab",
    "OTHER_NONCURRENT_LIAB": "oth_ncl",
    "TOTAL_LIABILITIES": "total_liab",
    "CAPITAL_RESERVE": "cap_rese",
    "SURPLUS_RESERVE": "surplus_rese",
    "UNASSIGN_PROFIT": "undistr_porfit",
    "TOTAL_PARENT_EQUITY": "total_hldr_eqy_exc_min_int",
    "TOTAL_EQUITY": "total_hldr_eqy_inc_min_int",
    "MINORITY_EQUITY": "minority_int",
    "OTHER_RECE": "oth_receiv",
}

CASHFLOW_EM_TO_TS: dict[str, str] = {
    "SECUCODE": "ts_code",
    "NOTICE_DATE": "ann_date",
    "UPDATE_DATE": "f_ann_date",
    "REPORT_DATE": "end_date",
    "REPORT_TYPE": "report_type_name",
    "NETPROFIT": "net_profit",
    "NETCASH_OPERATE": "n_cashflow_act",
    "NETCASH_INVEST": "n_cashflow_inv",
    "NETCASH_FINANCE": "n_cash_flows_fnc_act",
    "SALES_SERVICES": "c_fr_sale_sg",
    "BUY_SERVICES": "c_paid_goods_s",
    "PAY_STAFF_CASH": "c_paid_to_for_empl",
    "PAY_ALL_TAX": "c_paid_for_taxes",
    "END_CASH": "c_cash_equ_end_period",
}

# 同花顺指标中文列 → fina_indicator-ish
INDICATOR_THS_TO_TS: dict[str, str] = {
    "日期": "end_date",
    "净资产收益率(%)": "roe",
    "加权净资产收益率(%)": "roe_waa",
    "销售毛利率(%)": "grossprofit_margin",
    "销售净利率(%)": "netprofit_margin",
    "资产负债率(%)": "debt_to_assets",
    "摊薄每股收益(元)": "eps",
    "每股经营性现金流(元)": "ocfps",
    "总资产净利润率(%)": "roa",
}

# Columns financial_audit / data_snapshot treat as critical for A-share
CRITICAL_INCOME = ("total_revenue", "revenue", "n_income_attr_p", "operate_profit", "invest_income")
CRITICAL_BALANCE = ("total_assets", "total_liab", "money_cap", "contract_liab", "oth_ncl")
CRITICAL_CASHFLOW = ("n_cashflow_act", "n_cashflow_inv", "n_cash_flows_fnc_act")

# Tushare-shaped balance columns promised after bridge (P0 replacement for
# TushareCollector._BALANCE_CORE_FIELDS — keep contract_liab / oth_ncl covered).
BALANCE_CORE_TS_FIELDS = ",".join(sorted(set(BALANCE_EM_TO_TS.values())))


def _ymd(series: pd.Series) -> pd.Series:
    dt = pd.to_datetime(series, errors="coerce")
    return dt.dt.strftime("%Y%m%d")


def rename_map(df: pd.DataFrame, mapping: dict[str, str]) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    # case-insensitive match on columns
    upper = {c.upper(): c for c in out.columns}
    ren = {}
    for src, dst in mapping.items():
        if src in out.columns:
            ren[src] = dst
        elif src.upper() in upper:
            ren[upper[src.upper()]] = dst
    out = out.rename(columns=ren)
    for col in ("ann_date", "f_ann_date", "end_date", "trade_date"):
        if col in out.columns:
            out[col] = _ymd(out[col])
    if "ts_code" in out.columns:
        out["ts_code"] = out["ts_code"].astype(str).str.upper()
    return out


def bridge_income(df: pd.DataFrame) -> pd.DataFrame:
    return rename_map(df, INCOME_EM_TO_TS)


def bridge_balancesheet(df: pd.DataFrame) -> pd.DataFrame:
    return rename_map(df, BALANCE_EM_TO_TS)


def bridge_cashflow(df: pd.DataFrame) -> pd.DataFrame:
    return rename_map(df, CASHFLOW_EM_TO_TS)


def bridge_indicator_ths(df: pd.DataFrame) -> pd.DataFrame:
    return rename_map(df, INDICATOR_THS_TO_TS)


def missing_critical(df: pd.DataFrame, required: Iterable[str]) -> list[str]:
    if df is None or df.empty:
        return list(required)
    return [c for c in required if c not in df.columns or df[c].isna().all()]


# ---------------------------------------------------------------------------
# P1 governance / calendar bridges (Chinese EM/Sina/Cninfo → Tushare-shaped)
# ---------------------------------------------------------------------------


def bridge_holders(df: pd.DataFrame, ts_code: str, *, float_mode: bool = False) -> pd.DataFrame:
    """Map main/circulate holders → top10_* columns."""
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    ren = {}
    for c in out.columns:
        s = str(c)
        if s in ("股东名称",):
            ren[c] = "holder_name"
        elif s in ("持股数量",):
            ren[c] = "hold_amount"
        elif s in ("持股比例",) and not float_mode:
            ren[c] = "hold_ratio"
        elif s in ("占流通股比例",) or (float_mode and "流通" in s and "比例" in s):
            ren[c] = "hold_float_ratio"
        elif s in ("截至日期", "截止日期"):
            ren[c] = "end_date"
        elif s in ("公告日期",):
            ren[c] = "ann_date"
        elif s in ("股本性质",):
            ren[c] = "holder_type"
        elif s in ("编号",):
            ren[c] = "rank"
    out = out.rename(columns=ren)
    for col in ("end_date", "ann_date"):
        if col in out.columns:
            out[col] = _ymd(out[col])
    out["ts_code"] = ts_code
    if "hold_ratio" not in out.columns and "hold_float_ratio" in out.columns:
        # circulate table: use float ratio as hold_ratio for downstream totals
        out["hold_ratio"] = pd.to_numeric(out["hold_float_ratio"], errors="coerce")
    if "hold_float_ratio" not in out.columns:
        out["hold_float_ratio"] = None
    if "hold_change" not in out.columns:
        out["hold_change"] = None
    if "holder_type" not in out.columns:
        out["holder_type"] = None
    keep = [
        c
        for c in (
            "ts_code",
            "ann_date",
            "end_date",
            "holder_name",
            "hold_amount",
            "hold_ratio",
            "hold_float_ratio",
            "hold_change",
            "holder_type",
            "rank",
        )
        if c in out.columns
    ]
    return out[keep].reset_index(drop=True)


def bridge_holdernumber(df: pd.DataFrame, ts_code: str) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    ren = {}
    for c in out.columns:
        s = str(c)
        if "统计截止日" in s or s == "截止日期":
            ren[c] = "end_date"
        elif s in ("股东户数-本次", "股东户数"):
            ren[c] = "holder_num"
        elif "公告日期" in s:
            ren[c] = "ann_date"
    out = out.rename(columns=ren)
    if "end_date" not in out.columns:
        return pd.DataFrame()
    out["end_date"] = _ymd(out["end_date"])
    if "ann_date" in out.columns:
        out["ann_date"] = _ymd(out["ann_date"])
    out["ts_code"] = ts_code
    out["holder_num"] = pd.to_numeric(out.get("holder_num"), errors="coerce")
    return out[["ts_code", "ann_date", "end_date", "holder_num"]].reset_index(drop=True) if "ann_date" in out.columns else out[["ts_code", "end_date", "holder_num"]].reset_index(drop=True)


def bridge_pledge(df: pd.DataFrame, ts_code: str) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    ren = {}
    for c in out.columns:
        s = str(c)
        if "股东" in s and "名称" in s:
            ren[c] = "holder_name"
        elif "质押方" in s or "质权" in s:
            ren[c] = "pledgor"
        elif s in ("质押股份数量", "质押股数", "质押数量"):
            ren[c] = "pledge_amount"
        elif "占总股本" in s and "比例" in s:
            ren[c] = "h_total_ratio"
        elif "占持股" in s and "比例" in s:
            ren[c] = "p_total_ratio"
        elif "开始" in s and "日期" in s:
            ren[c] = "start_date"
        elif ("结束" in s or "到期" in s) and "日期" in s:
            ren[c] = "end_date"
        elif "公告" in s and "日期" in s:
            ren[c] = "ann_date"
        elif "状态" in s or "是否解押" in s or "解除" in s:
            ren[c] = "is_release"
    out = out.rename(columns=ren)
    for col in ("ann_date", "start_date", "end_date"):
        if col in out.columns:
            out[col] = _ymd(out[col])
    out["ts_code"] = ts_code
    for col in ("holder_name", "pledgor", "pledge_amount", "p_total_ratio", "h_total_ratio", "is_release"):
        if col not in out.columns:
            out[col] = None
    keep = ["ts_code", "ann_date", "holder_name", "pledgor", "pledge_amount", "start_date", "end_date", "p_total_ratio", "h_total_ratio", "is_release"]
    return out[[c for c in keep if c in out.columns]].reset_index(drop=True)


def bridge_stk_managers_stub(ts_code: str) -> pd.DataFrame:
    return pd.DataFrame(columns=["ts_code", "ann_date", "name", "gender", "lev", "title", "edu", "national", "birthday", "begin_date", "end_date"])


def bridge_repurchase(df: pd.DataFrame, ts_code: str) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    ren = {}
    for c in out.columns:
        s = str(c)
        if s == "最新公告日期":
            ren[c] = "ann_date"
        elif s == "回购起始时间":
            ren[c] = "proc"
        elif "已回购股份数量" in s:
            ren[c] = "vol"
        elif "已回购金额" in s:
            ren[c] = "amount"
        elif s == "实施进度":
            ren[c] = "progress"
    out = out.rename(columns=ren)
    if "ann_date" in out.columns:
        out["ann_date"] = _ymd(out["ann_date"])
    out["ts_code"] = ts_code
    keep = [c for c in ("ts_code", "ann_date", "proc", "vol", "amount", "progress") if c in out.columns]
    return out[keep].reset_index(drop=True)


def bridge_forecast(df: pd.DataFrame, ts_code: str) -> pd.DataFrame:
    """EM 业绩预告 → forecast_vip-ish (net_profit_min/max in 万元)."""
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    rows = []
    for _, r in out.iterrows():
        end = str(r.get("_end_date") or "")
        ann = r.get("公告日期")
        ann_s = _ymd(pd.Series([ann])).iloc[0] if ann is not None else ""
        ftype = r.get("预告类型") or r.get("预测指标") or ""
        # 预测数值 may be single; 业绩变动幅度 may be range text
        val = pd.to_numeric(r.get("预测数值"), errors="coerce")
        # EM 预测数值 often in 元 for 净利润 → convert to 万元 for snapshot
        npmin = npmax = None
        if pd.notna(val):
            wan = float(val) / 1e4 if abs(float(val)) > 1e5 else float(val)
            npmin = npmax = wan
        # try parse 业绩变动 like "1000万元至1500万元"
        chg = str(r.get("业绩变动") or "")
        m = None
        import re

        nums = re.findall(r"([-+]?\d[\d,]*(?:\.\d+)?)\s*万", chg)
        if len(nums) >= 2:
            try:
                npmin = float(nums[0].replace(",", ""))
                npmax = float(nums[1].replace(",", ""))
            except ValueError:
                pass
        rows.append(
            {
                "ts_code": ts_code,
                "ann_date": ann_s,
                "end_date": end,
                "type": str(ftype),
                "p_change_min": None,
                "p_change_max": None,
                "net_profit_min": npmin,
                "net_profit_max": npmax,
                "summary": chg[:200],
            }
        )
    return pd.DataFrame(rows)


def bridge_express(df: pd.DataFrame, ts_code: str) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    rows = []
    for _, r in df.iterrows():
        end = str(r.get("_end_date") or "")
        ann = r.get("公告日期")
        ann_s = _ymd(pd.Series([ann])).iloc[0] if ann is not None else ""
        rev = pd.to_numeric(r.get("营业收入-营业收入"), errors="coerce")
        n_income = pd.to_numeric(r.get("净利润-净利润"), errors="coerce")
        rows.append(
            {
                "ts_code": ts_code,
                "ann_date": ann_s,
                "end_date": end,
                "revenue": float(rev) if pd.notna(rev) else None,
                "n_income": float(n_income) if pd.notna(n_income) else None,
                "yoy_net_profit": pd.to_numeric(r.get("净利润-同比增长"), errors="coerce"),
                "yoy_sales": pd.to_numeric(r.get("营业收入-同比增长"), errors="coerce"),
                "roe": pd.to_numeric(r.get("净资产收益率"), errors="coerce"),
            }
        )
    return pd.DataFrame(rows)


def bridge_dividend(df: pd.DataFrame, ts_code: str) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    ren = {}
    for c in out.columns:
        s = str(c)
        if "实施方案公告日期" in s or s == "公告日期":
            ren[c] = "ann_date"
        elif s == "股权登记日":
            ren[c] = "record_date"
        elif s == "除权日":
            ren[c] = "ex_date"
        elif s == "派息日":
            ren[c] = "pay_date"
        elif s == "派息比例":
            ren[c] = "cash_div_tax"
        elif s == "送股比例":
            ren[c] = "stk_div"
        elif s == "转增比例":
            ren[c] = "stk_bo_rate"
        elif "分红说明" in s or "实施方案分红说明" in s:
            ren[c] = "div_proc"
    out = out.rename(columns=ren)
    for col in ("ann_date", "record_date", "ex_date", "pay_date"):
        if col in out.columns:
            out[col] = _ymd(out[col])
    out["ts_code"] = ts_code
    keep = [c for c in ("ts_code", "ann_date", "record_date", "ex_date", "pay_date", "cash_div_tax", "stk_div", "stk_bo_rate", "div_proc") if c in out.columns]
    return out[keep].reset_index(drop=True)


def bridge_disclosure_date(df: pd.DataFrame, ts_code: str) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    rows = []
    for _, r in df.iterrows():
        period = str(r.get("_period") or "")
        # map period text → end_date approx
        end = ""
        if "年报" in period:
            y = "".join(ch for ch in period if ch.isdigit())[:4]
            end = f"{y}1231" if y else ""
        elif "三季" in period:
            y = "".join(ch for ch in period if ch.isdigit())[:4]
            end = f"{y}0930" if y else ""
        elif "半年" in period:
            y = "".join(ch for ch in period if ch.isdigit())[:4]
            end = f"{y}0630" if y else ""
        elif "一季" in period:
            y = "".join(ch for ch in period if ch.isdigit())[:4]
            end = f"{y}0331" if y else ""
        pre = r.get("首次预约")
        actual = r.get("实际披露")
        modify = r.get("三次变更")
        if pd.isna(modify):
            modify = r.get("二次变更")
        if pd.isna(modify):
            modify = r.get("初次变更")
        pre_s = (
            _ymd(pd.Series([pre])).iloc[0]
            if pre is not None and not (isinstance(pre, float) and pd.isna(pre))
            else None
        )
        rows.append(
            {
                "ts_code": ts_code,
                "end_date": end,
                "pre_date": pre_s,
                "pre_ann_date": pre_s,  # alias for older Tushare-shaped consumers / monitor
                "actual_date": _ymd(pd.Series([actual])).iloc[0]
                if actual is not None and not (isinstance(actual, float) and pd.isna(actual))
                else None,
                "modify_date": _ymd(pd.Series([modify])).iloc[0]
                if modify is not None and not (isinstance(modify, float) and pd.isna(modify))
                else None,
            }
        )
    return pd.DataFrame(rows)


def bridge_share_float(df: pd.DataFrame, ts_code: str) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    ren = {}
    for c in out.columns:
        s = str(c)
        if s == "解禁日期":
            ren[c] = "float_date"
        elif s == "公告日期":
            ren[c] = "ann_date"
        elif s in ("解禁数量",):
            ren[c] = "float_share"
        elif "股东" in s:
            ren[c] = "holder_name"
        elif "类型" in s or "批次" in s:
            ren[c] = "share_type"
    out = out.rename(columns=ren)
    for col in ("float_date", "ann_date"):
        if col in out.columns:
            out[col] = _ymd(out[col])
    out["ts_code"] = ts_code
    if "float_ratio" not in out.columns:
        out["float_ratio"] = None
    if "holder_name" not in out.columns:
        out["holder_name"] = None
    if "share_type" not in out.columns:
        out["share_type"] = None
    # Sina 解禁数量 often 万股 already — keep as-is (snapshot formats as number)
    keep = [c for c in ("ts_code", "ann_date", "float_date", "float_share", "float_ratio", "holder_name", "share_type") if c in out.columns]
    return out[keep].reset_index(drop=True)


def bridge_block_trade(df: pd.DataFrame, ts_code: str) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    ren = {}
    for c in out.columns:
        s = str(c)
        if s == "交易日期":
            ren[c] = "trade_date"
        elif s == "成交价":
            ren[c] = "price"
        elif s == "成交量":
            ren[c] = "vol"
        elif s == "成交额":
            ren[c] = "amount"
        elif s == "买方营业部":
            ren[c] = "buyer"
        elif s == "卖方营业部":
            ren[c] = "seller"
    out = out.rename(columns=ren)
    if "trade_date" in out.columns:
        out["trade_date"] = _ymd(out["trade_date"])
    out["ts_code"] = ts_code
    # EM 成交额 often 元 → Tushare amount 万元
    if "amount" in out.columns:
        amt = pd.to_numeric(out["amount"], errors="coerce")
        out["amount"] = amt.apply(lambda x: x / 10000.0 if pd.notna(x) and abs(x) > 1e5 else x)
    keep = [c for c in ("ts_code", "trade_date", "price", "vol", "amount", "buyer", "seller") if c in out.columns]
    return out[keep].reset_index(drop=True)
