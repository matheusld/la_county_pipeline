"""Consensus reliability metrics for merged scorer outputs."""

from __future__ import annotations

from typing import Any

from sklearn.metrics import cohen_kappa_score


def final_tier_from_avg(row: dict[str, Any]) -> int:
    """Return final tier after the legacy intersection ceiling."""
    cf = float(row["avg_score_carefirst"])
    ag = float(row["avg_score_ai_governance"])
    ix = min(float(row["avg_score_intersection"]), min(cf, ag) + 2)
    ev = float(row["avg_score_evidentiary"])
    composite = cf * 0.25 + ag * 0.25 + ix * 0.35 + ev * 0.15
    if composite >= 6.0 and (cf >= 5 or ag >= 5):
        return 1
    if composite >= 3.5:
        return 2
    if composite >= 1.0:
        return 3
    return 4


def _kappa_pair(left: list[int], right: list[int]) -> dict[str, float]:
    same = sum(1 for a, b in zip(left, right) if a == b)
    return {
        "unweighted_kappa": float(cohen_kappa_score(left, right)),
        "quadratic_weighted_kappa": float(cohen_kappa_score(left, right, weights="quadratic")),
        "same_tier_pct": same / len(left) * 100 if left else 0.0,
    }


def consensus_kappas(rows: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    """Compute raw inter-model and resolved-tier kappas.

    Resolved-tier kappas are not independent inter-rater reliability. They
    measure agreement between each scorer and the tier assigned after combining
    both scorers' outputs.
    """
    shared = [
        row
        for row in rows
        if row.get("tier_claude") is not None and row.get("tier_gpt") is not None
    ]
    claude = [int(row["tier_claude"]) for row in shared]
    gpt = [int(row["tier_gpt"]) for row in shared]
    avg = [int(row["tier_avg"]) for row in shared]
    final = [final_tier_from_avg(row) for row in shared]
    return {
        "claude_vs_gpt": _kappa_pair(claude, gpt),
        "claude_vs_avg": _kappa_pair(claude, avg),
        "gpt_vs_avg": _kappa_pair(gpt, avg),
        "claude_vs_final": _kappa_pair(claude, final),
        "gpt_vs_final": _kappa_pair(gpt, final),
    }
