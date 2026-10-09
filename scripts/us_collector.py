"""US product path removed (P0). Original module: attic/us_collector.py."""
from __future__ import annotations


class USCollector:
    def __init__(self, *args, **kwargs):
        raise RuntimeError("US market support removed in P0 — A-share only. See attic/us_collector.py")

    def collect_all(self, *args, **kwargs):
        raise RuntimeError("US market support removed in P0 — A-share only")
