"""
Domain models shared across the pipeline.

ExtractedField keeps the original text (raw), the normalized value, a
confidence score and the page it came from. Reviewer corrections never
overwrite these; they are recorded separately in review_actions.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any


class Outcome(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"


class Severity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class DecisionStatus(str, Enum):
    READY_FOR_APPROVAL = "READY_FOR_APPROVAL"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    BLOCKED = "BLOCKED"


DECISION_LABELS = {
    "READY_FOR_APPROVAL": "Ready for approval",
    "NEEDS_REVIEW": "Needs review",
    "BLOCKED": "Blocked",
}


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------
@dataclass
class ExtractedField:
    value: Any = None
    raw: str | None = None
    confidence: Decimal = Decimal("0")
    source_page: int | None = None
    method: str | None = None
    warning: str | None = None
    bbox: tuple[float, float, float, float] | None = None  # (x0, y0, x1, y1) as fractions of the page

    @property
    def present(self) -> bool:
        return self.value is not None


@dataclass
class ExtractedLineItem:
    line_no: int
    description: str | None = None
    item_code: str | None = None
    quantity: Decimal | None = None
    uom: str | None = None
    unit_price: Decimal | None = None
    amount: Decimal | None = None
    tax_rate: Decimal | None = None
    tax_amount: Decimal | None = None
    raw: str | None = None
    confidence: Decimal = Decimal("0")
    source_page: int | None = None
    bbox: tuple[float, float, float, float] | None = None


HEADER_FIELDS = (
    "vendor_name", "vendor_address", "vendor_gstin", "buyer_gstin",
    "invoice_number", "invoice_date", "due_date", "po_number", "currency",
    "subtotal", "discount", "other_charges", "tax_amount", "total_amount",
)


@dataclass
class InvoiceDraft:
    header: dict[str, ExtractedField] = field(default_factory=dict)
    line_items: list[ExtractedLineItem] = field(default_factory=list)
    tax_lines: list[dict[str, Any]] = field(default_factory=list)  # e.g. IGST @18%
    extraction_method: str = ""
    provider: str = ""
    warnings: list[str] = field(default_factory=list)

    def get(self, name: str) -> Any:
        f = self.header.get(name)
        return f.value if f else None

    @property
    def missing_fields(self) -> list[str]:
        return [n for n in HEADER_FIELDS if not (self.header.get(n) and self.header[n].present)]


@dataclass
class DocumentText:
    """Output of the text-extraction stage."""
    pages: list[str]
    words: list[list[dict[str, Any]]]  # per page: pdfplumber-style word dicts
    method: str                        # digital_text / ocr_pdf / ocr_image
    page_count: int
    char_count: int
    ocr_confidence: Decimal | None = None
    tables: list[list[list[list[str | None]]]] = field(default_factory=list)  # per page
    page_sizes: list[tuple[float, float]] = field(default_factory=list)       # word-coordinate space


# ---------------------------------------------------------------------------
# Procurement master data
# ---------------------------------------------------------------------------
@dataclass
class Vendor:
    vendor_id: str
    legal_vendor_name: str
    display_name: str
    aliases: list[str]
    gstin: str | None
    status: str
    currency: str
    address: str
    state_code: str
    payment_terms: str


@dataclass
class POLine:
    po_number: str
    line_no: int
    item_code: str
    item_description: str
    uom: str
    quantity_ordered: Decimal
    unit_price: Decimal
    line_total: Decimal
    tax_rate: Decimal


@dataclass
class PurchaseOrder:
    po_number: str
    vendor_id: str
    po_date: str
    currency: str
    subtotal: Decimal
    tax_amount: Decimal
    total_po_amount: Decimal
    baseline_invoiced: Decimal
    po_status: str
    tolerance_pct: Decimal
    lines: list[POLine] = field(default_factory=list)
    invoiced_in_system: Decimal = Decimal("0")

    @property
    def amount_already_invoiced(self) -> Decimal:
        return self.baseline_invoiced + self.invoiced_in_system

    @property
    def remaining_balance(self) -> Decimal:
        """Remaining pre-tax balance available for invoicing."""
        return self.subtotal - self.amount_already_invoiced


# ---------------------------------------------------------------------------
# Validation and decision
# ---------------------------------------------------------------------------
@dataclass
class CheckResult:
    check_key: str
    category: str              # Extraction / Vendor / PO / Line items / Financial / Duplicate
    outcome: Outcome
    severity: Severity
    message: str
    expected: str | None = None
    actual: str | None = None
    field: str | None = None
    recommended_action: str | None = None


@dataclass
class Decision:
    status: DecisionStatus
    reason: str
    next_action: str
    summary_counts: dict[str, int]


# ---------------------------------------------------------------------------
# JSON helper
# ---------------------------------------------------------------------------
def to_jsonable(obj: Any) -> Any:
    if is_dataclass(obj) and not isinstance(obj, type):
        return to_jsonable(asdict(obj))
    if isinstance(obj, dict):
        return {k: to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(v) for v in obj]
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if isinstance(obj, Enum):
        return obj.value
    return obj
