# WebSearch 策略（A 股 · 免费多源）

> 本文件只定义 **WebSearch / WebFetch** 的用法。  
> 主数据源是 `scripts/a_share_collector.py`（akshare / 新浪 / 巨潮 providers）和 `scripts/pdf_reader.py`，见 `phases/phase1-data-collection.md`。  
> WebSearch 是**补洞与舆情**工具，不是财报主路径。
>
> **禁止**用于关键财务数据（收入、利润、PE、PB、ROE 等）——这些必须来自 **结构化免费源**（`[akshare:…]` / `[sina:…]`）或 **PDF 原文**（`[PDF:…]` / `[cninfo:…]`）。

---

## 1. 公告与 PDF URL

**A 股（主路径）**:

1. 先读 `raw_data/anns.parquet`（cninfo provider）里的标题 + PDF URL  
2. 仍缺时 WebSearch：`site:cninfo.com.cn {ticker} {company} {年}年年度报告 PDF`  
3. 备用：`site:sse.com.cn` / `site:szse.cn` 交易所公告检索

**不要**再走美股 SEC / 港股披露易——本 skill 仅 A 股。

---

## 2. 舆情与社区

**A 股**:

- 雪球 `site:xueqiu.com {company}`  
- 东方财富股吧 / 研报摘要页（只采观点，不采财务数字）  
- 近 12 月重大事项新闻（交易所问询、立案、回购、增减持）

看好 / 看衰各至少 3 条，写入 `sentiment.md`，带来源与日期。

---

## 3. 严禁用 WebSearch 当财报源

| 数据 | 必须走 |
|---|---|
| 最近 3 年营收 / 净利 / 毛利率 | `a_share_collector` → income / fina_indicator + PDF 交叉 |
| 当前 PE / PB / PS / 市值 | daily_basic（akshare）或本地推算 |
| 资产负债 / 现金流任一科目 | balancesheet / cashflow parquet 或年报 PDF |
| 前十大股东 | top10_holders + 定期报告 PDF |
| 股权质押 | pledge_detail；空表分 `empty_genuine` vs `source_failed` |
| 预约披露日 | C14 `disclosure_date` → `manifest --sync-disclosure-from` |

铁律：**关键数据必须有可审计锚点**。结构化源给数字，PDF 给「为什么变动」的管理层原文。

---

## 4. 降级策略（结构化源 / PDF 失败时）

1. 主源失败 → 备源（见改造方案字段簇矩阵）  
2. 整簇失败 → provenance `source_failed` + `data_sources.md` 缺口；**禁止**写成「无此事」  
3. 仅当结构化 + PDF 都不可用时，才允许 WebSearch 二手摘要，并在报告顶部标：

```
⚠️ 数据降级: 本次未能使用结构化免费源 / PDF 原文，仅依赖 WebSearch 二手摘要。
请核对网络与各站点可用性后重跑采集。
```

创业公司 / 未上市管线已移除，不在本 skill 范围。
