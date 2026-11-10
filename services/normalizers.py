"""
Deterministic normalization helpers.

Everything financial uses Decimal. Nothing here guesses: if a value cannot be
parsed reliably, the function returns None and the caller records it as missing.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

PAISA = Decimal("0.01")

# ---------------------------------------------------------------------------
# Money
# ---------------------------------------------------------------------------
_CURRENCY_TOKENS = ("₹", "rs.", "rs", "inr", "$", "usd")


def parse_amount(raw: str | None) -> Decimal | None:
    """Parse '₹ 9,45,000.00', 'Rs. 1,170.5', '(1,000.00)' into Decimal.

    Handles Indian digit grouping (lakh/crore) and western grouping alike,
    because grouping commas are simply removed.
    """
    if raw is None:
        return None
    s = str(raw).strip().lower().replace("/-", "")
    if not s:
        return None
    negative = s.startswith("(") and s.endswith(")") or s.startswith("-")
    for tok in _CURRENCY_TOKENS:
        s = s.replace(tok, "")
    s = s.replace(",", "").replace("(", "").replace(")", "").replace("-", "").strip()
    if not re.fullmatch(r"\d+(\.\d+)?", s):
        return None
    try:
        value = Decimal(s)
    except InvalidOperation:
        return None
    return -value if negative else value


def money(value: Decimal) -> Decimal:
    """Round to paise using banker-safe HALF_UP (standard for invoices)."""
    return value.quantize(PAISA, rounding=ROUND_HALF_UP)


def to_paise(value: Decimal | None) -> int | None:
    return None if value is None else int(money(value) * 100)


def from_paise(value: int | None) -> Decimal | None:
    return None if value is None else (Decimal(value) / 100).quantize(PAISA)


def format_inr(value: Decimal | None) -> str:
    """Indian digit grouping: 1115100 -> ₹11,15,100.00"""
    if value is None:
        return "—"
    v = money(value)
    sign = "-" if v < 0 else ""
    integer, frac = f"{abs(v):.2f}".split(".")
    if len(integer) > 3:
        head, tail = integer[:-3], integer[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        integer = ",".join(groups + [tail])
    return f"{sign}₹{integer}.{frac}"


def parse_quantity(raw: str | None) -> Decimal | None:
    if raw is None:
        return None
    s = str(raw).strip().replace(",", "")
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([A-Za-z]*)", s)
    return Decimal(m.group(1)) if m else None


def parse_percent(raw: str | None) -> Decimal | None:
    if raw is None:
        return None
    m = re.search(r"(\d+(?:\.\d+)?)\s*%", str(raw))
    return Decimal(m.group(1)) if m else None


# ---------------------------------------------------------------------------
# Dates
# ---------------------------------------------------------------------------
_DATE_FORMATS = (
    "%d-%b-%Y", "%d %b %Y", "%d-%B-%Y", "%d %B %Y", "%b %d, %Y", "%B %d, %Y",
    "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y",
)


def parse_date(raw: str | None) -> date | None:
    """Day-first parsing (Indian convention). Ambiguous US-style is not assumed."""
    if not raw:
        return None
    s = re.sub(r"\s+", " ", str(raw).strip().rstrip(".,"))
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------------------
# Identifiers and text
# ---------------------------------------------------------------------------
_LEGAL_SUFFIXES = (
    "private limited", "pvt. ltd.", "pvt ltd", "pvt. ltd", "pvt.ltd.", "pvt.ltd",
    "limited", "ltd.", "ltd", "llp", "inc.", "inc", "co.",
)


def normalize_name(name: str | None) -> str:
    """Lowercase, strip punctuation and legal suffixes for name comparison."""
    if not name:
        return ""
    s = name.lower().strip()
    for suf in _LEGAL_SUFFIXES:
        if s.endswith(" " + suf):
            s = s[: -len(suf) - 1]
            break
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def normalize_invoice_number(num: str | None) -> str:
    """'DELL/INV/2026/00418' and 'dell-inv-2026-418' normalize identically."""
    if not num:
        return ""
    parts = re.split(r"[^A-Za-z0-9]+", num.upper())
    parts = [(p.lstrip("0") or "0") if p.isdigit() else p for p in parts if p]
    return "".join(parts)


def normalize_text(s: str | None) -> str:
    if not s:
        return ""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", s.lower())).strip()


# ---------------------------------------------------------------------------
# GSTIN (Indian GST registration number)
# Format: 2-digit state code + 10-char PAN + entity no. + 'Z' + checksum
# ---------------------------------------------------------------------------
_GSTIN_RE = re.compile(r"^\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
_GSTIN_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def gstin_checksum(first14: str) -> str:
    """Official GSTIN mod-36 check character."""
    total = 0
    for i, ch in enumerate(first14.upper()):
        product = _GSTIN_CHARS.index(ch) * (1 if i % 2 == 0 else 2)
        total += product // 36 + product % 36
    return _GSTIN_CHARS[(36 - total % 36) % 36]


def normalize_gstin(raw: str | None) -> str | None:
    if not raw:
        return None
    s = re.sub(r"[^0-9A-Za-z]", "", raw).upper()
    return s or None


def validate_gstin(gstin: str | None) -> tuple[bool, str]:
    """Return (is_valid, reason)."""
    if not gstin:
        return False, "GSTIN not present"
    if not _GSTIN_RE.match(gstin):
        return False, "GSTIN format is invalid"
    if gstin_checksum(gstin[:14]) != gstin[14]:
        return False, "GSTIN checksum does not match"
    return True, "GSTIN format and checksum valid"
