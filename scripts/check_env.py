"""Environment sanity check — run before any collector to diagnose missing pieces.

Usage:
    python3 -m scripts.check_env
"""
from __future__ import annotations

import importlib
import sys

REQUIRED_PKGS = [
    "akshare",
    "pypdf",
    "pandas",
    "pyarrow",
    "requests",
    # v8 契约层与出片
    "yaml",
    "jsonschema",
    "markdown",
]


def check() -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass

    from . import config

    print("=== company-analysis skill env check (P0 A-share free sources) ===\n")
    ok = True

    print(f"Python: {sys.version.split()[0]}")

    print("\nRequired packages:")
    for pkg in REQUIRED_PKGS:
        try:
            m = importlib.import_module(pkg)
            ver = getattr(m, "__version__", "?")
            print(f"  [OK] {pkg} {ver}")
        except ImportError:
            print(f"  [MISSING] {pkg}  → pip3 install --user {pkg}")
            ok = False

    print("\nData vendor tokens:")
    print("  [OK] Tushare not required (removed in P0)")
    if config.TUSHARE_TOKEN:
        print("  [INFO] TUSHARE_TOKEN is set but ignored — safe to unset")

    print(f"\nCache: {config.CACHE_DIR}  (TTL={config.CACHE_TTL_DAYS} days)")
    print(f"Output: {config.OUTPUT_ROOT}")
    print(f"HTTP timeout: {config.HTTP_TIMEOUT_SEC}s  rate limit: {config.HTTP_RATE_LIMIT_SEC}s")

    print("\n" + ("✅ All checks passed." if ok else "⚠️  Fix the [MISSING] items above."))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(check())
