"""Provider protocol, provenance, and empty-table semantics (P0)."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

import pandas as pd


class SourceStatus(str, Enum):
    """Empty-table semantics — never treat source_failed as 'no event'."""

    OK = "ok"
    EMPTY_GENUINE = "empty_genuine"  # source answered; truly no rows
    SOURCE_FAILED = "source_failed"  # error / timeout / blocked
    PARTIAL = "partial"  # some fields filled, others missing
    DEFERRED = "deferred"  # intentionally not fetched this phase (e.g. moneyflow P1)


@dataclass
class Provenance:
    cluster: str
    primary: str
    status: SourceStatus
    secondary: str | None = None
    used: str | None = None  # which source won
    rows: int = 0
    note: str = ""
    conflicts: list[str] = field(default_factory=list)
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d


@dataclass
class ClusterResult:
    name: str
    df: pd.DataFrame
    provenance: Provenance

    @property
    def ok_for_core(self) -> bool:
        """Core clusters (statements/quotes) require real rows."""
        return self.provenance.status in (SourceStatus.OK, SourceStatus.PARTIAL) and not self.df.empty


def failed(cluster: str, primary: str, err: Exception | str, secondary: str | None = None) -> ClusterResult:
    msg = str(err)
    return ClusterResult(
        name=cluster,
        df=pd.DataFrame(),
        provenance=Provenance(
            cluster=cluster,
            primary=primary,
            secondary=secondary,
            used=None,
            status=SourceStatus.SOURCE_FAILED,
            rows=0,
            error=msg,
            note="source_failed — do not interpret as absence of the underlying event",
        ),
    )


def empty_genuine(cluster: str, primary: str, note: str = "") -> ClusterResult:
    return ClusterResult(
        name=cluster,
        df=pd.DataFrame(),
        provenance=Provenance(
            cluster=cluster,
            primary=primary,
            used=primary,
            status=SourceStatus.EMPTY_GENUINE,
            rows=0,
            note=note or "source returned zero rows",
        ),
    )


def ok(cluster: str, df: pd.DataFrame, primary: str, secondary: str | None = None, note: str = "") -> ClusterResult:
    return ClusterResult(
        name=cluster,
        df=df,
        provenance=Provenance(
            cluster=cluster,
            primary=primary,
            secondary=secondary,
            used=primary,
            status=SourceStatus.OK if not df.empty else SourceStatus.EMPTY_GENUINE,
            rows=len(df),
            note=note,
        ),
    )


def deferred(cluster: str, reason: str) -> ClusterResult:
    return ClusterResult(
        name=cluster,
        df=pd.DataFrame(),
        provenance=Provenance(
            cluster=cluster,
            primary="none",
            status=SourceStatus.DEFERRED,
            rows=0,
            note=reason,
        ),
    )
