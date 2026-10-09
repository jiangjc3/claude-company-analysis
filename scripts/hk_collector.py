"""HK product path removed (P0). Original module: attic/hk_collector.py."""
from __future__ import annotations


class HKCollector:
    def __init__(self, *args, **kwargs):
        raise RuntimeError("HK market support removed in P0 — A-share only. See attic/hk_collector.py")

    def collect_all(self, *args, **kwargs):
        raise RuntimeError("HK market support removed in P0 — A-share only")
