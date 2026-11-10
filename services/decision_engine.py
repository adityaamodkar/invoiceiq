"""
Deterministic decision engine.

    any CRITICAL result          -> BLOCKED
    else any WARNING result      -> NEEDS REVIEW
    else                         -> READY FOR APPROVAL

No LLM is involved. The reason text is built from the results themselves.
"""
from __future__ import annotations

from services.models import CheckResult, Decision, DecisionStatus, Severity

NO_PAYMENT = "No payment has been initiated."

# Root causes first: a duplicate explains a "PO exhausted" failure, not the reverse.
CATEGORY_PRIORITY = ["Document", "Duplicate", "Vendor", "Purchase order", "Extraction", "Line items", "Financial"]


def _prioritise(items: list[CheckResult]) -> list[CheckResult]:
    rank = {c: i for i, c in enumerate(CATEGORY_PRIORITY)}
    return sorted(items, key=lambda r: rank.get(r.category, len(rank)))


def _reason(lead: str, items: list[CheckResult]) -> str:
    """Root cause first; remaining issues are counted, and listed in full under Checks."""
    text = f"{lead}{items[0].message}"
    if len(items) > 1:
        text += f" {len(items) - 1} further issue(s) are listed under Checks."
    return text


def decide(results: list[CheckResult]) -> Decision:
    critical = _prioritise([r for r in results if r.severity == Severity.CRITICAL])
    warnings = _prioritise([r for r in results if r.severity == Severity.WARNING])
    counts = {"total": len(results), "critical": len(critical), "warning": len(warnings),
              "passed": len(results) - len(critical) - len(warnings)}

    if critical:
        reason = _reason("", critical)
        action = critical[0].recommended_action or "Escalate to the AP lead."
        return Decision(DecisionStatus.BLOCKED, reason, f"{action} {NO_PAYMENT}", counts)
    if warnings:
        reason = _reason(f"{len(warnings)} item(s) need human confirmation. ", warnings)
        action = (f"Open the review queue and resolve {len(warnings)} item(s), "
                  f"starting with: {warnings[0].recommended_action or warnings[0].message}")
        return Decision(DecisionStatus.NEEDS_REVIEW, reason, f"{action} {NO_PAYMENT}", counts)
    return Decision(
        DecisionStatus.READY_FOR_APPROVAL,
        f"All {len(results)} checks passed: vendor verified, PO matched, amounts within tolerance, "
        f"no duplicate found.",
        f"Forward to the approver for payment approval. {NO_PAYMENT}", counts)
