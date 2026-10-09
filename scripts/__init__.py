"""company-analysis data layer — structured financial data collection & computation.

P0: A-share only, free multi-source (akshare / sina / cninfo). No Tushare.

Modules:
    config              配置（缓存 TTL、HTTP 限速）
    check_env           环境检查（pip 包；无 token）
    a_share_collector   A 股采集门面
    providers / merge   多源 provider + merge 规则
    schema_bridge       外部列 → 旧 Tushare 形列名
    pdf_reader          财报 PDF 原文解析
    derived_metrics     CAGR / FCF / … 计算
"""

__version__ = "8.10.0-p0"
