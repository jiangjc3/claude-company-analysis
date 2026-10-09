"""Tushare removed from the product path (P0). Use ``scripts.a_share_collector``.

Importing ``TushareCollector`` raises. CLI redirects to the free multi-source facade.
Attic copies were deleted in P3 (plan D4).
"""
from __future__ import annotations

import sys
import warnings


class TushareCollector:
    def __init__(self, *args, **kwargs):
        raise RuntimeError(
            "TushareCollector was removed (A-share free multi-source rebuild). "
            "Use: python3 -m scripts.a_share_collector <code> --name <company>"
        )


def save_bundle(*args, **kwargs):
    from .a_share_collector import save_bundle as _save

    return _save(*args, **kwargs)


def main(argv=None) -> int:
    warnings.warn(
        "scripts.tushare_collector is deprecated. Redirecting to a_share_collector…",
        DeprecationWarning,
        stacklevel=2,
    )
    from .a_share_collector import main as amain

    return amain(argv)


if __name__ == "__main__":
    sys.exit(main())
