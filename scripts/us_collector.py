"""US product path removed (P0). Kept as import stub so old call sites fail loudly."""


class USCollector:
    def __init__(self, *args, **kwargs):
        raise RuntimeError("US market support removed — A-share only")

    def collect_all(self, *args, **kwargs):
        raise RuntimeError("US market support removed — A-share only")
