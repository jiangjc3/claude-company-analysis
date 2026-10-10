# 数据源与合规（短页）

本 skill **仅支持 A 股**（沪 / 深 / 北交所）。数据采集走免费公开源组合，**不需要也不接受 Tushare token**。

## 用到哪些源

| 簇 | 主源 | 备源 / 备注 |
|---|---|---|
| 三表 / 财务指标 | akshare（东财等封装） | 本地 `derived_metrics` 重算对照 |
| 日线 | 新浪 K 线 | akshare 日线 |
| 估值快照 | akshare | 日线 × 股本估算 |
| 公告 / PDF | 巨潮 cninfo | 交易所公告检索降级 |
| 股东 / 质押 / 解禁 / 大宗等 | akshare | 年报 PDF 精读补洞 |
| 高管名单 / 薪酬持股 | 东财 F10 `CompanyManagement/PageAjax` | 薪酬字段偶发全空 → `partial`；年报 PDF 权威 |
| 资金流 / 北向 / 两融 / 龙虎榜 | akshare / 东财 | **最脆**；失败必须在附录 E 标缺口 |
| 龙虎榜机构席位 | akshare `stock_lhb_stock_detail_em`（机构*席位）+ `stock_lhb_jgmmtj_em` 备源 | 窗口无上榜 → `empty_genuine` |
| Peer | 公开行业成分 + 市值 | 推荐 `--peer-codes` 手改错配 |

列名尽量兼容旧 Tushare 形 parquet，便于审计与装配脚本少改；**运行时不再调用 Tushare**。

## 空表语义（必读）

每个簇写入 provenance：`ok` | `empty_genuine` | `source_failed` | `partial` | `deferred`。

| 状态 | 含义 | 报告里不能写成 |
|---|---|---|
| `empty_genuine` | 源答了「零行」 | —（可写「窗口内无记录」，仍建议交叉公告） |
| `source_failed` | 源挂了 / 被拦 | 「无质押」「无资金异动」「无大宗」 |
| `partial` | 只有部分字段 | 「数据齐全」 |
| `deferred` | 本阶段故意不采 / 无稳免费 API | 「公司未披露」 |

附录 E（`data_sources.md`）是缺口总账；双 reviewer 会查「把缺口伪装成公司事实」。

## 诚实空表（已接线，仍禁止伪装）

以下簇**已有**免费单票源，但失败 / 字段缺失时仍不得写成「公司无高管 / 无薪酬 / 无机构席位」：

| 簇 | 主源 | 常见非 ok |
|---|---|---|
| `stk_managers` | 东财 F10 gglb | `source_failed` / 偶发 `empty_genuine` |
| `stk_rewards` | 同上 SALARY/HOLD_NUM | 名册有、薪酬全空 → `partial`（去年报） |
| `top_inst` | LHB 席位明细含「机构」；备源 jgmmtj 机构合计 | 窗口无机构上榜 → `empty_genuine` |

## 合规与使用边界

- **研究与学习用途**。不是投资建议，不提供交易执行或行情再分发服务。
- 优先走 akshare 已封装接口与巨潮公开检索；控制并发与缓存（默认约 7 日 TTL，复查可设 `CA_CACHE_MAX_AGE_DAYS=0`）。
- User-Agent 保持诚实；支持用户自备已下载 PDF，减少爬取面。
- 网站 ToS / 反爬政策可能变化；源失败时 skill 应降级而不是编造。
- 保留报告内「非投资建议」免责声明；仓位表述仅出现在⑤决策节点。

## 本地复现

```bash
python -m scripts.check_env          # 无 TUSHARE_TOKEN 要求
python -m scripts.a_share_collector 600519.SH --name 贵州茅台
# 可选实网烟测（默认 CI 跳过）:
CA_NETWORK_TESTS=1 python -m unittest scripts.tests.test_a_share_p0.TestNetworkSmoke
```

可选实网 CI：仓库内模板 [`optional-network-nightly.workflow.yml`](./optional-network-nightly.workflow.yml)。复制到 `.github/workflows/network-nightly.yml` 即可启用（定时 / 手动；`continue-on-error`，不挡合并）。默认 PR CI 仍只跑离线单测。

更多贡献约定见根目录 [`CONTRIBUTING.md`](../CONTRIBUTING.md)。
