"""
Structured extraction: picks a provider and assesses extraction quality.

Provider order: LLM (only if configured AND implemented) -> rule-based.
The UI always shows which provider actually ran.
"""
from __future__ import annotations

from config import settings
from services.extraction.base import ExtractionProvider
from services.extraction.llm import LLMProvider
from services.extraction.rules import RuleBasedProvider
from services.models import (
    CheckResult, DocumentText, InvoiceDraft, Outcome, Severity,
)

FIELD_LABELS = {
    "vendor_name": "Vendor name", "vendor_address": "Vendor address",
    "vendor_gstin": "Vendor GSTIN", "buyer_gstin": "Buyer GSTIN",
    "invoice_number": "Invoice number", "invoice_date": "Invoice date",
    "due_date": "Due date", "po_number": "PO number", "currency": "Currency",
    "subtotal": "Subtotal", "discount": "Discount", "other_charges": "Other charges",
    "tax_amount": "Tax amount", "total_amount": "Total amount",
}


CORROBORATED_LATER = {"vendor_name"}


def select_provider() -> tuple[ExtractionProvider, list[str]]:
    """Return the provider to use and status notes explaining the choice."""
    notes = []
    llm = LLMProvider()
    ok, status = llm.is_available()
    notes.append(status)
    if ok:
        return llm, notes
    notes.append("Using rule-based extraction")
    return RuleBasedProvider(), notes


def extract_invoice(doc: DocumentText) -> tuple[InvoiceDraft, list[str]]:
    provider, notes = select_provider()
    return provider.extract(doc), notes


def check_extraction(draft: InvoiceDraft) -> list[CheckResult]:
    """Required fields present and confident enough to rely on."""
    results: list[CheckResult] = []
    missing = [f for f in settings.REQUIRED_HEADER_FIELDS if not draft.header.get(f)
               or not draft.header[f].present]
    if missing:
        names = ", ".join(FIELD_LABELS[m] for m in missing)
        results.append(CheckResult(
            "required_fields", "Extraction", Outcome.WARN, Severity.WARNING,
            f"Required information missing from the invoice: {names}.",
            expected="All required fields present", actual=f"Missing: {names}",
            field=missing[0],
            recommended_action="Check the original document and enter the missing values, "
                               "or request a corrected invoice from the vendor."))
    else:
        results.append(CheckResult(
            "required_fields", "Extraction", Outcome.PASS, Severity.INFO,
            "All required fields were extracted."))

    # vendor_name is excluded here: vendor verification accepts a low-confidence name only
    # when it exactly matches an approved name or alias (see vendor_matcher).
    low = [(n, f) for n, f in draft.header.items()
           if f.present and n in settings.REQUIRED_HEADER_FIELDS and n not in CORROBORATED_LATER
           and f.confidence < settings.MIN_FIELD_CONFIDENCE]
    low_lines = [li for li in draft.line_items if li.confidence < settings.MIN_FIELD_CONFIDENCE]
    if low or low_lines:
        parts = [f"{FIELD_LABELS[n]} ({f.confidence:.2f})" for n, f in low]
        if low_lines:
            parts.append(f"{len(low_lines)} line item(s)")
        results.append(CheckResult(
            "extraction_confidence", "Extraction", Outcome.WARN, Severity.WARNING,
            "Some values were read with low confidence: " + ", ".join(parts) + ".",
            expected=f">= {settings.MIN_FIELD_CONFIDENCE}", actual=", ".join(parts),
            field=low[0][0] if low else "line_items",
            recommended_action="Compare these values against the original document and correct them if needed."))
    else:
        results.append(CheckResult(
            "extraction_confidence", "Extraction", Outcome.PASS, Severity.INFO,
            f"All required values extracted with confidence >= {settings.MIN_FIELD_CONFIDENCE}."))

    if not draft.line_items:
        results.append(CheckResult(
            "line_items_present", "Extraction", Outcome.WARN, Severity.WARNING,
            "No line items could be identified, so quantities and prices cannot be checked.",
            field="line_items",
            recommended_action="Review the invoice layout and enter line items manually."))
    return results
