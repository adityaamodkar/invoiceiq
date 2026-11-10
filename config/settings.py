"""
Central configuration for InvoiceIQ.

Business rules (tolerances, thresholds, required fields) live here, NOT inside
the validators. Validators read these values, so a policy change never needs a
code change in the validation logic.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths (all relative to the project root so they work locally and on Linux)
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
SAMPLE_DIR = PROJECT_ROOT / "sample_documents"
VAR_DIR = PROJECT_ROOT / "var"  # runtime state; git-ignored

DB_PATH = Path(os.getenv("INVOICEIQ_DB_PATH", str(VAR_DIR / "invoiceiq.db")))

VENDORS_CSV = DATA_DIR / "vendors.csv"
PURCHASE_ORDERS_CSV = DATA_DIR / "purchase_orders.csv"
PO_LINES_CSV = DATA_DIR / "po_line_items.csv"


# ---------------------------------------------------------------------------
# The buying company (the entity that receives invoices)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class BuyerProfile:
    legal_name: str = "Northwind Components Pvt Ltd"
    gstin: str = "36AAACN5678K1ZZ"
    state_code: str = "36"  # Telangana
    address: str = "Plot 14, Phase II, IDA Patancheru, Sangareddy, Telangana 502319"


BUYER = BuyerProfile()


# ---------------------------------------------------------------------------
# Tolerance policy (agreed with the business owner)
#   variance <= pass_pct            -> PASS (info note)
#   pass_pct < variance <= review   -> NEEDS REVIEW
#   variance > review_pct           -> BLOCKED
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class TolerancePolicy:
    amount_pass_pct: Decimal = Decimal("1")       # default; a PO may override
    amount_review_upper_pct: Decimal = Decimal("10")
    unit_price_pass_pct: Decimal = Decimal("0")   # price must match the PO exactly
    unit_price_review_upper_pct: Decimal = Decimal("10")
    arithmetic_rounding_abs: Decimal = Decimal("1.00")  # ₹1 rounding allowance
    tax_rounding_abs: Decimal = Decimal("1.00")


TOLERANCE = TolerancePolicy()


# ---------------------------------------------------------------------------
# Extraction / review thresholds
# ---------------------------------------------------------------------------
MIN_FIELD_CONFIDENCE = Decimal("0.80")

REQUIRED_HEADER_FIELDS = (
    "vendor_name",
    "invoice_number",
    "invoice_date",
    "subtotal",
    "total_amount",
)

# Duplicate detection: "possible duplicate" window for same vendor + same amount
POSSIBLE_DUPLICATE_WINDOW_DAYS = 45

# PO balance is drawn down by an invoice that the checks cleared (unless a person rejects it)
# or that a person approved after review. See database/repository.CONSUMES.

# Upload limits
MAX_UPLOAD_MB = 15
SUPPORTED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}

# A PDF page with fewer extractable characters than this is treated as scanned
MIN_TEXT_CHARS_PER_PAGE = 40

# ---------------------------------------------------------------------------
# Optional LLM extraction provider (no key is ever hardcoded)
# ---------------------------------------------------------------------------
def _secret(name: str) -> str | None:
    """Read from env first, then Streamlit secrets if available."""
    val = os.getenv(name)
    if val:
        return val
    try:
        import streamlit as st  # local import: config must not require streamlit

        return st.secrets.get(name)  # type: ignore[no-any-return]
    except Exception:
        return None


@dataclass(frozen=True)
class LLMConfig:
    provider: str | None = field(default_factory=lambda: _secret("INVOICEIQ_LLM_PROVIDER"))
    api_key: str | None = field(default_factory=lambda: _secret("INVOICEIQ_LLM_API_KEY"))
    model: str | None = field(default_factory=lambda: _secret("INVOICEIQ_LLM_MODEL"))

    @property
    def is_configured(self) -> bool:
        return bool(self.provider and self.api_key)

# Pause between pipeline stages so a live audience can follow the run view.
# Measured stage durations exclude this pause. Set to 0 for production-speed runs.
DEMO_PACE_SECONDS = float(os.getenv("INVOICEIQ_DEMO_PACE_SECONDS", "0.3"))

# Display timezone for timestamps in the UI (stored as UTC)
DISPLAY_TZ = os.getenv("INVOICEIQ_DISPLAY_TZ", "Asia/Kolkata")
