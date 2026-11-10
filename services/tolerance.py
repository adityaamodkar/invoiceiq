"""
Tolerance band evaluation (agreed policy):

    variance <= pass_pct                 -> PASS  (INFO note when variance > 0)
    pass_pct < variance <= review_pct    -> WARN  (NEEDS REVIEW)
    variance > review_pct                -> FAIL  (BLOCKED)

Variance % = |actual - reference| / reference x 100
Only adverse variances (billing MORE than the reference) are evaluated against
the bands; billing less is reported as a favourable variance and passes.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from services.models import Outcome, Severity


@dataclass
class Band:
    outcome: Outcome
    severity: Severity
    difference: Decimal
    variance_pct: Decimal | None   # None when the reference is zero
    band_label: str


def evaluate(actual: Decimal, reference: Decimal, pass_pct: Decimal, review_pct: Decimal) -> Band:
    diff = actual - reference
    if diff <= 0:
        pct = (abs(diff) / reference * 100).quantize(Decimal("0.01")) if reference else Decimal("0")
        label = "exact match" if diff == 0 else "below reference (favourable)"
        return Band(Outcome.PASS, Severity.INFO, diff, pct, label)
    if reference <= 0:
        return Band(Outcome.FAIL, Severity.CRITICAL, diff, None, "no balance available")
    pct = (diff / reference * 100).quantize(Decimal("0.01"))
    if pct <= pass_pct:
        return Band(Outcome.PASS, Severity.INFO, diff, pct, f"within {pass_pct}% tolerance")
    above = "exceeds PO (exact match required)" if pass_pct == 0 else f"above {pass_pct}% tolerance"
    if pct <= review_pct:
        return Band(Outcome.WARN, Severity.WARNING, diff, pct, f"{above}, within {review_pct}% review band")
    return Band(Outcome.FAIL, Severity.CRITICAL, diff, pct, f"above {review_pct}% review band")
