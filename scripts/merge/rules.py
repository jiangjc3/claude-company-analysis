"""Multi-source merge rules (P0 defaults from a-share-rebuild-plan)."""
from __future__ import annotations

from typing import Iterable

import pandas as pd

from ..providers.base import ClusterResult, Provenance, SourceStatus, failed


def pick_first_ok(cluster: str, candidates: Iterable[ClusterResult]) -> ClusterResult:
    """Primary-first: first non-failed result with rows wins; else first empty_genuine; else last failure."""
    cands = list(candidates)
    if not cands:
        return failed(cluster, "none", "no providers registered")

    with_rows = [c for c in cands if c.provenance.status in (SourceStatus.OK, SourceStatus.PARTIAL) and not c.df.empty]
    if with_rows:
        winner = with_rows[0]
        winner.provenance.used = winner.provenance.primary
        if len(with_rows) > 1:
            winner.provenance.secondary = with_rows[1].provenance.primary
        return winner

    genuine = [c for c in cands if c.provenance.status == SourceStatus.EMPTY_GENUINE]
    if genuine:
        return genuine[0]

    deferred = [c for c in cands if c.provenance.status == SourceStatus.DEFERRED]
    if deferred and all(c.provenance.status == SourceStatus.DEFERRED for c in cands):
        return deferred[0]

    # all failed — combine errors
    last = cands[-1]
    errs = "; ".join(f"{c.provenance.primary}:{c.provenance.error}" for c in cands if c.provenance.error)
    last.provenance.status = SourceStatus.SOURCE_FAILED
    last.provenance.error = errs or last.provenance.error
    last.provenance.note = "all sources failed — do not treat as empty_genuine"
    return last


def merge_frames(
    cluster: str,
    primary: ClusterResult,
    secondary: ClusterResult | None,
    *,
    key: str,
    conflict_rel_tol: float = 0.05,
) -> ClusterResult:
    """Outer-align on key; keep primary values on conflict; record conflicts (no silent average)."""
    if secondary is None or secondary.df.empty:
        return primary
    if primary.df.empty:
        out = secondary
        out.provenance.used = secondary.provenance.primary
        out.provenance.secondary = primary.provenance.primary
        out.provenance.note = (out.provenance.note + " | filled from secondary after primary empty").strip(" |")
        return out

    if key not in primary.df.columns or key not in secondary.df.columns:
        return primary

    left = primary.df.copy()
    right = secondary.df.copy()
    conflicts: list[str] = []
    merged = left.merge(right, on=key, how="outer", suffixes=("", "_sec"))
    for col in list(left.columns):
        if col == key:
            continue
        sec = f"{col}_sec"
        if sec not in merged.columns:
            continue
        both = merged[col].notna() & merged[sec].notna()
        if both.any():
            try:
                a = pd.to_numeric(merged.loc[both, col], errors="coerce")
                b = pd.to_numeric(merged.loc[both, sec], errors="coerce")
                denom = a.abs().clip(lower=1e-9)
                rel = ((a - b).abs() / denom)
                bad = rel > conflict_rel_tol
                if bad.any():
                    conflicts.append(f"{col}: {int(bad.sum())} rows diverge >{conflict_rel_tol:.0%}")
            except Exception:  # noqa: BLE001
                pass
        # fill holes from secondary; never overwrite primary numbers
        need = merged[col].isna() & merged[sec].notna()
        merged.loc[need, col] = merged.loc[need, sec]
        merged.drop(columns=[sec], inplace=True)

    status = SourceStatus.PARTIAL if conflicts or merged[list(left.columns)].isna().any().any() else SourceStatus.OK
    prov = Provenance(
        cluster=cluster,
        primary=primary.provenance.primary,
        secondary=secondary.provenance.primary,
        used=primary.provenance.primary,
        status=status,
        rows=len(merged),
        note="merged primary+secondary; conflicts keep primary",
        conflicts=conflicts,
    )
    return ClusterResult(name=cluster, df=merged, provenance=prov)
