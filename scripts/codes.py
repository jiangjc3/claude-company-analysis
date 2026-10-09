"""A-share / (legacy) HK code normalization — shared, no data vendor dependency."""
from __future__ import annotations

import re

_A_SHARE_PATTERN = re.compile(r"^(\d{6})(?:\.(SH|SZ|BJ))?$", re.IGNORECASE)
_HK_PATTERN = re.compile(r"^(\d{1,5})(?:\.HK)?$", re.IGNORECASE)


def normalize_a_code(code: str) -> str:
    """'002862' → '002862.SZ'; '600519' → '600519.SH'; '920522' → '920522.BJ'."""
    code = code.strip().upper()
    m = _A_SHARE_PATTERN.match(code)
    if not m:
        raise ValueError(f"Not a valid A-share code: {code!r}")
    num, suffix = m.group(1), m.group(2)
    if suffix:
        return f"{num}.{suffix}"
    first = num[0]
    if first == "6":
        return f"{num}.SH"
    if first in "03":
        return f"{num}.SZ"
    if first in "489":
        return f"{num}.BJ"
    raise ValueError(f"Unknown market prefix for {code!r}")


def normalize_hk_code(code: str) -> str:
    """Legacy helper (HK product path removed in P0). Kept for attic imports."""
    code = code.strip().upper()
    m = _HK_PATTERN.match(code)
    if not m:
        raise ValueError(f"Not a valid HK code: {code!r}")
    return f"{m.group(1).zfill(4)}.HK"


def to_em_secid(ts_code: str) -> str:
    """'600519.SH' → 'SH600519' (Eastmoney / akshare report APIs)."""
    ts_code = normalize_a_code(ts_code)
    num, suf = ts_code.split(".")
    return f"{suf}{num}"


def to_symbol6(ts_code: str) -> str:
    """'600519.SH' → '600519'."""
    return normalize_a_code(ts_code).split(".")[0]
