"""
SQLite connection, schema and seeding.

Money columns are INTEGER paise (₹1 = 100) so sums are exact in SQL.
Only database/repository.py and this module touch SQL, so moving to a managed
database later means rewriting these two files only.
"""
from __future__ import annotations

import csv
import sqlite3
from contextlib import contextmanager
from decimal import Decimal
from pathlib import Path
from typing import Iterator

from config import settings
from services.normalizers import to_paise

SCHEMA = """
CREATE TABLE IF NOT EXISTS vendors (
    vendor_id TEXT PRIMARY KEY,
    legal_vendor_name TEXT NOT NULL,
    display_name TEXT,
    aliases TEXT,
    gstin TEXT,
    status TEXT NOT NULL,
    currency TEXT NOT NULL,
    address TEXT,
    state_code TEXT,
    payment_terms TEXT
);

CREATE TABLE IF NOT EXISTS purchase_orders (
    po_number TEXT PRIMARY KEY,
    vendor_id TEXT NOT NULL REFERENCES vendors(vendor_id),
    po_date TEXT,
    currency TEXT NOT NULL,
    subtotal_paise INTEGER NOT NULL,
    tax_paise INTEGER NOT NULL,
    total_paise INTEGER NOT NULL,
    baseline_invoiced_paise INTEGER NOT NULL DEFAULT 0,
    po_status TEXT NOT NULL,
    tolerance_pct TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS po_line_items (
    po_number TEXT NOT NULL REFERENCES purchase_orders(po_number),
    line_no INTEGER NOT NULL,
    item_code TEXT,
    item_description TEXT,
    uom TEXT,
    quantity_ordered TEXT NOT NULL,
    unit_price_paise INTEGER NOT NULL,
    line_total_paise INTEGER NOT NULL,
    tax_rate TEXT,
    PRIMARY KEY (po_number, line_no)
);

CREATE TABLE IF NOT EXISTS processing_runs (
    run_id TEXT PRIMARY KEY,
    parent_run_id TEXT,
    is_current INTEGER NOT NULL DEFAULT 1,
    file_name TEXT,
    file_type TEXT,
    file_size_bytes INTEGER,
    file_sha256 TEXT,
    uploaded_at TEXT,
    started_at TEXT,
    finished_at TEXT,
    run_status TEXT NOT NULL,            -- RUNNING / COMPLETED / FAILED
    decision TEXT,                       -- READY_FOR_APPROVAL / NEEDS_REVIEW / BLOCKED
    decision_reason TEXT,
    next_action TEXT,
    failure_stage TEXT,
    failure_reason TEXT,
    extraction_method TEXT,
    approval_status TEXT,                -- NULL (pending) / APPROVED / REJECTED, set by a person
    approval_note TEXT,
    approval_at TEXT
);

CREATE TABLE IF NOT EXISTS invoices (
    run_id TEXT PRIMARY KEY REFERENCES processing_runs(run_id),
    vendor_id TEXT,
    vendor_name TEXT,
    vendor_gstin TEXT,
    invoice_number TEXT,
    invoice_number_norm TEXT,
    invoice_date TEXT,
    po_number TEXT,
    currency TEXT,
    subtotal_paise INTEGER,
    tax_paise INTEGER,
    total_paise INTEGER,
    raw_extraction_json TEXT,
    normalized_json TEXT
);

CREATE TABLE IF NOT EXISTS invoice_line_items (
    run_id TEXT NOT NULL REFERENCES processing_runs(run_id),
    line_no INTEGER NOT NULL,
    description TEXT,
    item_code TEXT,
    quantity TEXT,
    uom TEXT,
    unit_price_paise INTEGER,
    amount_paise INTEGER,
    matched_po_line INTEGER,
    PRIMARY KEY (run_id, line_no)
);

CREATE TABLE IF NOT EXISTS stage_events (
    run_id TEXT NOT NULL REFERENCES processing_runs(run_id),
    seq INTEGER NOT NULL,
    stage_key TEXT NOT NULL,
    stage_name TEXT NOT NULL,
    status TEXT NOT NULL,
    message TEXT,
    output_json TEXT,
    duration_ms INTEGER,
    recorded_at TEXT,
    PRIMARY KEY (run_id, seq)
);

CREATE TABLE IF NOT EXISTS validation_results (
    run_id TEXT NOT NULL REFERENCES processing_runs(run_id),
    seq INTEGER NOT NULL,
    check_key TEXT NOT NULL,
    category TEXT NOT NULL,
    outcome TEXT NOT NULL,                -- PASS / WARN / FAIL
    severity TEXT NOT NULL,               -- INFO / WARNING / CRITICAL
    message TEXT,
    expected TEXT,
    actual TEXT,
    field TEXT,
    recommended_action TEXT,
    PRIMARY KEY (run_id, seq)
);

CREATE TABLE IF NOT EXISTS exceptions (
    exception_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES processing_runs(run_id),
    category TEXT NOT NULL,
    severity TEXT NOT NULL,
    summary TEXT,
    suggested_action TEXT,
    status TEXT NOT NULL DEFAULT 'OPEN',
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS review_actions (
    action_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES processing_runs(run_id),
    new_run_id TEXT,
    field TEXT,
    original_value TEXT,
    corrected_value TEXT,
    action TEXT NOT NULL,
    reason TEXT,
    reviewer TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS app_prefs (key TEXT PRIMARY KEY, value TEXT);

CREATE INDEX IF NOT EXISTS idx_invoices_vendor_num ON invoices(vendor_id, invoice_number_norm);
CREATE INDEX IF NOT EXISTS idx_runs_sha ON processing_runs(file_sha256);
"""

TRANSACTIONAL_TABLES = (
    "review_actions", "exceptions", "validation_results", "stage_events",
    "invoice_line_items", "invoices", "processing_runs",
)
MASTER_TABLES = ("po_line_items", "purchase_orders", "vendors")


@contextmanager
def connect(db_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    path = Path(db_path or settings.DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


MIGRATIONS = (
    "ALTER TABLE processing_runs ADD COLUMN approval_status TEXT",
    "ALTER TABLE processing_runs ADD COLUMN approval_note TEXT",
    "ALTER TABLE processing_runs ADD COLUMN approval_at TEXT",
)


def _migrate(conn) -> None:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(processing_runs)")}
    for stmt in MIGRATIONS:
        if stmt.split("ADD COLUMN ")[1].split()[0] not in cols:
            conn.execute(stmt)


def init_db(db_path: Path | None = None) -> None:
    """Create tables and seed procurement data if the database is empty."""
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)
        _migrate(conn)
        count = conn.execute("SELECT COUNT(*) FROM vendors").fetchone()[0]
        if count == 0:
            _seed_master_data(conn)


def reset_demo_data(db_path: Path | None = None, include_master: bool = True) -> None:
    """Clear processing history (and optionally reload procurement seed data)."""
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)
        for t in TRANSACTIONAL_TABLES:
            conn.execute(f"DELETE FROM {t}")
        if include_master:
            for t in MASTER_TABLES:
                conn.execute(f"DELETE FROM {t}")
            _seed_master_data(conn)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _seed_master_data(conn: sqlite3.Connection) -> None:
    for v in _read_csv(settings.VENDORS_CSV):
        conn.execute(
            "INSERT INTO vendors VALUES (?,?,?,?,?,?,?,?,?,?)",
            (v["vendor_id"], v["legal_vendor_name"], v["display_name"], v["aliases"],
             v["gstin"], v["status"], v["currency"], v["address"], v["state_code"],
             v["payment_terms"]),
        )
    for p in _read_csv(settings.PURCHASE_ORDERS_CSV):
        conn.execute(
            "INSERT INTO purchase_orders VALUES (?,?,?,?,?,?,?,?,?,?)",
            (p["po_number"], p["vendor_id"], p["po_date"], p["currency"],
             to_paise(Decimal(p["subtotal"])), to_paise(Decimal(p["tax_amount"])),
             to_paise(Decimal(p["total_po_amount"])),
             to_paise(Decimal(p["baseline_invoiced_amount"])),
             p["po_status"], p["tolerance_percentage"]),
        )
    for li in _read_csv(settings.PO_LINES_CSV):
        conn.execute(
            "INSERT INTO po_line_items VALUES (?,?,?,?,?,?,?,?,?)",
            (li["po_number"], int(li["line_no"]), li["item_code"], li["item_description"],
             li["uom"], li["quantity_ordered"], to_paise(Decimal(li["unit_price"])),
             to_paise(Decimal(li["line_total"])), li["tax_rate"]),
        )
