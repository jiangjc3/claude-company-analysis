# 在 Cursor 里跑全量公司分析（P0）

本 fork 的**交付运行时是 Cursor Project / cloud·local agents**，不是 Claude Code。  
判断链手册与 `agents/*.md` 仍复用；调度入口换成本文件 + `scripts/cursor_run.py`。

## 一句话

在 Cursor Project 说 **「跑某某公司」** → coordinator 按下面命令执行。

## 前置

```bash
cd <repo-root>
python3 -m scripts.check_env   # 需 akshare 等；无需 Tushare
```

## 命令

| 意图 | 命令 |
|---|---|
| 解析名称/代码 | `python3 -m scripts.cursor_run resolve --query 宁德时代` |
| 机器采集（Phase 1） | `python3 -m scripts.cursor_run collect --query 宁德时代` |
| 导入已有 pack | `python3 -m scripts.cursor_run import-pack --pack <dir> --company 宁德时代 --ticker 300750.SZ` |
| 生成 worker prompts | `python3 -m scripts.cursor_run emit-prompts --company 宁德时代` |
| 看进度 | `python3 -m scripts.cursor_run status --company 宁德时代` |
| 节点齐后出片 | `python3 -m scripts.cursor_run assemble --company 宁德时代` |

`collect` 会跑：`init_run` → `a_share_collector` → audit / metrics / snapshot / red_flags / technical / capital / peer。

## 判断链（LLM workers）

`emit-prompts` 在 `output/{company}/runs/{date}/cursor_prompts/` 写下填好路径的 brief：

| 文件 | 角色 | 波次 |
|---|---|---|
| `00-orchestrator.md` | coordinator checklist | — |
| `01-data-collector-gaps.md` | 补 PDF/舆情 | 可选 |
| `02-doc-analyst.md` | Phase 2 | 串行 |
| `03a` / `03b` | 质地 / 赔率 | 波 1 并行 |
| `03c` / `03d` | 路径 / 状态 | 波 2 并行 |
| `03e-decision-writer.md` | 决策 | 波 3 |
| `06a` / `06b` | 双 reviewer | assemble 之后 |

Worker 读对应 `agents/*.md` + `references/*`，只写自己的产物，自跑 `verdict_block` / `check_phase2`。  
主协调器**不手改**节点 YAML；修正用 Fresh-Restart。

详细映射见 Project store `docs/cursor-runtime-plan.md`。编排说明：`agents/cursor/orchestrator.md`。

## 宁德时代续跑（现成 pack）

若 Project store 已有 `media/ningde-times/`：

```bash
python3 -m scripts.cursor_run import-pack \
  --pack /cursor/stores/self/media/ningde-times \
  --company 宁德时代 --ticker 300750.SZ
python3 -m scripts.cursor_run emit-prompts --company 宁德时代
python3 -m scripts.cursor_run status --company 宁德时代
# → 按 cursor_prompts/ 派 Cursor workers 写节点，再：
python3 -m scripts.cursor_run assemble --company 宁德时代
```

## 与 Claude Code 的关系

| | Claude Code | Cursor（现行） |
|---|---|---|
| 入口 | `/company-analysis` | 「跑某某公司」+ `cursor_run` |
| Sub-agent | `Agent(subagent_type=…)` | Cursor workers / Tasks + `cursor_prompts/` |
| 数据层 | 同左 | **同一套** `a_share_collector` |
| 装配/lint/HTML | 同左 | `cursor_run assemble` |

`SKILL.md` 仍描述判断链协议，但**不再要求**安装到 `~/.claude/skills/` 才能交付。
