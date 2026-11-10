"""
Vendor verification.

Identity signals, strongest first:
  1. GSTIN exact match (a legal tax registration, validated by checksum)
  2. Legal name or approved alias (normalized exact match)
  3. Fuzzy name similarity - only ever a SUGGESTION, never a verification
"""
from __future__ import annotations

from difflib import SequenceMatcher

from config import settings
from services.models import CheckResult, InvoiceDraft, Outcome, Severity, Vendor
from services.normalizers import normalize_gstin, normalize_name, validate_gstin

FUZZY_SUGGEST_THRESHOLD = 0.80


def _names(v: Vendor) -> set[str]:
    return {normalize_name(n) for n in [v.legal_vendor_name, v.display_name, *v.aliases] if n}


def verify_vendor(draft: InvoiceDraft, vendors: list[Vendor]) -> tuple[Vendor | None, list[CheckResult], dict]:
    results: list[CheckResult] = []
    name = draft.get("vendor_name")
    gstin = normalize_gstin(draft.get("vendor_gstin"))
    name_norm = normalize_name(name)

    by_gstin = next((v for v in vendors if v.gstin and v.gstin == gstin), None) if gstin else None
    by_name = [v for v in vendors if name_norm and name_norm in _names(v)]
    evidence = {"invoice_vendor_name": name, "invoice_gstin": gstin,
                "gstin_match": by_gstin.vendor_id if by_gstin else None,
                "name_matches": [v.vendor_id for v in by_name]}

    # GSTIN format / checksum
    if gstin:
        ok, why = validate_gstin(gstin)
        results.append(CheckResult(
            "vendor_gstin_format", "Vendor", Outcome.PASS if ok else Outcome.WARN,
            Severity.INFO if ok else Severity.WARNING,
            f"Vendor GSTIN {gstin}: {why}.", expected="Valid GSTIN format and checksum", actual=gstin, field="vendor_gstin",
            recommended_action=None if ok else "Confirm the GSTIN with the vendor; it may be mistyped or misread."))

    vendor: Vendor | None = None
    if by_gstin and (not name_norm or by_gstin in by_name):
        vendor = by_gstin
        how = "GSTIN and legal name" if name_norm and normalize_name(by_gstin.legal_vendor_name) == name_norm \
            else ("GSTIN and approved alias" if name_norm else "GSTIN (name not found on invoice)")
        results.append(CheckResult(
            "vendor_identity", "Vendor", Outcome.PASS, Severity.INFO,
            f"Vendor identified as {vendor.vendor_id} {vendor.legal_vendor_name} by {how}.",
            expected=f"{vendor.legal_vendor_name} / {vendor.gstin}", actual=f"{name} / {gstin}",
            field="vendor_name"))
    elif by_gstin and by_name:  # GSTIN says A, name says B
        results.append(CheckResult(
            "vendor_identity", "Vendor", Outcome.FAIL, Severity.CRITICAL,
            f"Conflicting vendor identity: GSTIN belongs to {by_gstin.vendor_id} "
            f"{by_gstin.legal_vendor_name} but the name matches {by_name[0].vendor_id} "
            f"{by_name[0].legal_vendor_name}.",
            expected=f"{by_gstin.legal_vendor_name}", actual=f"{name}", field="vendor_gstin",
            recommended_action="Do not process. Contact the vendor through a known channel to confirm "
                               "their registration and bank details."))
    elif by_gstin:  # GSTIN known, name not recognised
        vendor = by_gstin
        results.append(CheckResult(
            "vendor_identity", "Vendor", Outcome.WARN, Severity.WARNING,
            f"GSTIN matches {by_gstin.vendor_id} {by_gstin.legal_vendor_name}, but the invoice name "
            f"'{name}' is not an approved name or alias.",
            expected=by_gstin.legal_vendor_name, actual=name, field="vendor_name",
            recommended_action="Confirm the trading name with procurement and add it as an alias if valid."))
    elif len(by_name) == 1:
        vendor = by_name[0]
        if gstin and vendor.gstin and gstin != vendor.gstin:
            results.append(CheckResult(
                "vendor_identity", "Vendor", Outcome.WARN, Severity.WARNING,
                f"Name matches {vendor.vendor_id} {vendor.legal_vendor_name}, but the invoice GSTIN "
                f"{gstin} differs from the registered GSTIN {vendor.gstin}.",
                expected=vendor.gstin, actual=gstin, field="vendor_gstin",
                recommended_action="Verify whether this is an additional registration of the same vendor "
                                   "before processing."))
        else:
            results.append(CheckResult(
                "vendor_identity", "Vendor", Outcome.WARN, Severity.WARNING,
                f"Vendor matched to {vendor.vendor_id} {vendor.legal_vendor_name} by name only; "
                f"no GSTIN was found on the invoice.",
                expected=vendor.gstin, actual="(not on invoice)", field="vendor_gstin",
                recommended_action="Confirm the vendor's GSTIN on the original document."))
    elif len(by_name) > 1:
        results.append(CheckResult(
            "vendor_identity", "Vendor", Outcome.WARN, Severity.WARNING,
            f"Vendor name '{name}' matches more than one approved vendor: "
            f"{', '.join(v.vendor_id for v in by_name)}.",
            actual=name, field="vendor_name",
            recommended_action="Select the correct vendor record."))
    else:
        best = max(vendors, key=lambda v: max(
            (SequenceMatcher(None, name_norm, n).ratio() for n in _names(v)), default=0), default=None)
        score = max((SequenceMatcher(None, name_norm, n).ratio() for n in _names(best)), default=0) if best else 0
        if best and name_norm and score >= FUZZY_SUGGEST_THRESHOLD:
            results.append(CheckResult(
                "vendor_identity", "Vendor", Outcome.WARN, Severity.WARNING,
                f"Vendor '{name}' is not an exact approved name. Closest match: {best.vendor_id} "
                f"{best.legal_vendor_name} (similarity {score:.0%}). Not verified automatically.",
                expected=best.legal_vendor_name, actual=name, field="vendor_name",
                recommended_action="Confirm whether this is the same vendor."))
            evidence["suggested_vendor"] = best.vendor_id
        else:
            results.append(CheckResult(
                "vendor_identity", "Vendor", Outcome.FAIL, Severity.CRITICAL,
                f"Vendor '{name or '(not found)'}' is not in the approved vendor master.",
                actual=name, field="vendor_name",
                recommended_action="Route to procurement: the vendor must be onboarded and approved "
                                   "before any invoice can be processed."))

    name_field = draft.header.get("vendor_name")
    if name_field and name_field.present and name_field.confidence < settings.MIN_FIELD_CONFIDENCE:
        exact = vendor is not None and name_norm in _names(vendor)
        results.append(CheckResult(
            "vendor_name_confidence", "Vendor", Outcome.PASS if exact else Outcome.WARN,
            Severity.INFO if exact else Severity.WARNING,
            (f"Vendor name was read with low confidence ({name_field.confidence:.2f}) but exactly matches "
             f"the approved record, so it is corroborated.") if exact else
            f"Vendor name was read with low confidence ({name_field.confidence:.2f}) and is not an exact "
            f"approved name.", actual=name, field="vendor_name",
            recommended_action=None if exact else "Check the vendor name on the original document."))

    if vendor:
        active = vendor.status.lower() == "active"
        results.append(CheckResult(
            "vendor_status", "Vendor", Outcome.PASS if active else Outcome.FAIL,
            Severity.INFO if active else Severity.CRITICAL,
            f"Vendor {vendor.vendor_id} status is {vendor.status}.",
            expected="Active", actual=vendor.status, field="vendor_name",
            recommended_action=None if active else
            "Do not process invoices from inactive vendors. Escalate to procurement."))
        evidence["vendor_id"] = vendor.vendor_id
    return vendor, results, evidence
