"""DEPRECATED shim (P0).

Tushare has been removed from the product path. Use ``scripts.a_share_collector``.
This module only re-exports code helpers so older imports keep importing during transition.
"""
from __future__ import annotations

import sys
from typing import Any

import pandas as pd

from .codes import normalize_a_code, normalize_hk_code

__all__ = ["normalize_a_code", "normalize_hk_code", "TushareCollector", "save_bundle"]


class TushareCollector:
    """Removed — raises on use."""

    def __init__(self, *args: Any, **kwargs: Any):
        raise RuntimeError(
            "TushareCollector was removed in P0 (A-share free multi-source rebuild). "
            "Use: python3 -m scripts.a_share_collector <code> --name <company>"
        )


def save_bundle(bundle: dict[str, pd.DataFrame], out_dir) -> None:
    from .a_share_collector import save_bundle as _save

    _save(bundle, out_dir, provenance=None)


def main() -> int:
    print(
        "scripts.tushare_collector is deprecated. Redirecting to a_share_collector…",
        file=sys.stderr,
    )
    # Re-exec style: parse argv after module name
    from .a_share_collector import main as amain

    return amain()


if __name__ == "__main__":
    sys.exit(main())
