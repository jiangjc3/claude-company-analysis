"""Central configuration: cache paths, rate limits, output layout (P0: no Tushare)."""
from __future__ import annotations

import os
from pathlib import Path

# ---------- Deprecated (ignored) ----------
TUSHARE_TOKEN: str | None = os.environ.get("TUSHARE_TOKEN")  # ignored since P0

# ---------- 缓存 ----------
_DEFAULT_CACHE = Path.home() / ".claude" / "plugins" / "company-analysis" / ".cache"
CACHE_DIR: Path = Path(os.environ.get("COMPANY_ANALYSIS_CACHE", _DEFAULT_CACHE)).expanduser()
CACHE_TTL_DAYS: int = int(os.environ.get("COMPANY_ANALYSIS_CACHE_TTL", "7"))

# ---------- HTTP / free sources ----------
HTTP_TIMEOUT_SEC: float = float(os.environ.get("CA_HTTP_TIMEOUT", "30"))
HTTP_RATE_LIMIT_SEC: float = float(os.environ.get("CA_RATE_LIMIT", "0.35"))
HTTP_MAX_RETRIES: int = int(os.environ.get("CA_HTTP_MAX_RETRIES", "4"))
HTTP_RETRY_BACKOFF: float = float(os.environ.get("CA_HTTP_RETRY_BACKOFF", "1.5"))

# Legacy names kept so attic/tushare_collector still imports if someone runs it
TUSHARE_RATE_LIMIT_SEC: float = HTTP_RATE_LIMIT_SEC
TUSHARE_MAX_RETRIES: int = HTTP_MAX_RETRIES
TUSHARE_RETRY_BACKOFF: float = HTTP_RETRY_BACKOFF
YFINANCE_RATE_LIMIT_SEC: float = HTTP_RATE_LIMIT_SEC

# ---------- 输出目录 ----------
SKILL_ROOT: Path = Path(__file__).resolve().parent.parent
PLUGIN_ROOT: Path = SKILL_ROOT.parent.parent

if (PLUGIN_ROOT / "output").exists():
    OUTPUT_ROOT: Path = PLUGIN_ROOT / "output"
else:
    OUTPUT_ROOT = SKILL_ROOT / "output"


def output_dir(company: str) -> Path:
    for root in (PLUGIN_ROOT / "output", SKILL_ROOT / "output"):
        candidate = root / company
        if candidate.exists():
            (candidate / "raw_data").mkdir(exist_ok=True)
            (candidate / "raw_data" / "pdfs").mkdir(exist_ok=True)
            return candidate
    p = PLUGIN_ROOT / "output" / company
    p.mkdir(parents=True, exist_ok=True)
    (p / "raw_data").mkdir(exist_ok=True)
    (p / "raw_data" / "pdfs").mkdir(exist_ok=True)
    return p


def cache_path(key: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    safe = key.replace("/", "_").replace(":", "_")
    return CACHE_DIR / f"{safe}.parquet"
