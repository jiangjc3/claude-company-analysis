# scripts/ — Python 数据层

为 company-analysis skill 提供**结构化金融数据**（A 股免费多源，取代纯 WebSearch）：

- **`a_share_collector` + `providers/`** — akshare / 新浪 / 巨潮等，产出与旧契约兼容的 parquet
- **`pdf_reader`** — 解析财报 PDF 原文
- **`derived_metrics` / `financial_audit` / `capital_flow` / `peer_collector`** — 审计与对标
- **装配与质量环** — `assemble_report_v8` / `lint_v8` / `compare` / `build_html`

LLM（Phase 1/2/3）只负责**分析**，不再自己去搜索和拼凑核心数字。

**不需要 Tushare token。** 美股 / 港股采集器已移除（`us_collector` / `hk_collector` / `tushare_collector` 仅为大声失败的 import stub）。

数据源与合规短页：[`docs/data-sources-compliance.md`](../docs/data-sources-compliance.md)。

---

## 一次性配置

```bash
pip3 install --user -r scripts/requirements.txt
python3 -m scripts.check_env
```

可选环境变量见仓库根 `.env.sample`（`CA_HTTP_TIMEOUT` / `CA_RATE_LIMIT` / cache TTL 等）。

---

## 典型使用（A 股）

```bash
python3 -m scripts.a_share_collector 600519.SH --name 贵州茅台 --company-dir output/贵州茅台
python3 -m scripts.derived_metrics output/贵州茅台/raw_data/
```

对比（成员必须是 A 股）：

```bash
python3 -m scripts.compare candidates --anchor 东山精密
python3 -m scripts.compare init --anchor 东山精密 --anchor-ticker 002384.SZ \
  --slug pcb-optics --member "中际旭创:300308.SZ:library"
python3 -m scripts.compare assemble --slug pcb-optics
```

---

## 测试

```bash
python -m unittest discover -s scripts/tests -t . -v
# 可选实网:
CA_NETWORK_TESTS=1 python -m unittest scripts.tests.test_a_share_p0.TestNetworkSmoke -v
```

CI：`.github/workflows/tests.yml`（必过）；可选实网见 `docs/optional-network-nightly.workflow.yml`。
