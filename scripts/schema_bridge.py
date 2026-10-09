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
