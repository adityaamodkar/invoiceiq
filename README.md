# InvoiceIQ

InvoiceIQ turns a vendor invoice (PDF or image) into a verified, explainable
payment-readiness decision. It reads the document, checks it against the
company's procurement records (approved vendors, purchase orders, PO balances,
previously processed invoices) and returns one of three outcomes:

| Outcome | Meaning |
|---|---|
| **Ready for approval** | Every check passed. Forward to an approver. |
| **Needs review** | Something needs a person to confirm (low confidence, missing data, variance within the review band). |
| **Blocked** | A confirmed problem: exact duplicate, inactive or unknown vendor, wrong or closed PO, variance above the review band. |

InvoiceIQ **never initiates a payment**. Its job ends at the recommendation.

Built for the Zamp AI Solutions Analyst case study, Problem Statement 1 (Finance / AP).

---

## Run it locally

Requirements: Python 3.11 or newer. Tesseract is optional; you only need it for scanned PDFs and images.

```bash
# 1. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Install Tesseract to read scanned PDFs and photos (digital PDFs work without it)
#    macOS:   brew install tesseract
#    Ubuntu:  sudo apt-get install tesseract-ocr
#    Windows: https://github.com/UB-Mannheim/tesseract/wiki  (default install path is detected
#             automatically; otherwise set INVOICEIQ_TESSERACT_CMD to the full path of tesseract.exe)

# 4. Run the tests
python -m pytest -q

# 5. Start the app
streamlit run app.py
```

Open http://localhost:8501. Go to **Upload → Test invoices** and click **Process all 14**,
or pick one and process it to watch the steps live. Every result can be
opened in full (the document with highlights, what was read, the PO match, every check, the activity trail).
There are 14 test invoices (digital PDFs, scans, photocopies and photos); what each one exercises, and its expected outcome, is in `sample_documents/README.md`.

### The pages

| Page | What it is for |
|---|---|
| Home | Workload at a glance: needs review, ready to approve, blocked, approved this month, touchless rate; what needs attention; what falls due in 14 days; value by status; billed by vendor; PO utilisation; volume |
| Invoices | The inbox. Status tabs with counts, search, sort by due date or amount, flags per invoice, bulk approve / reject / delete |
| Invoice | The review screen: the document with extracted values boxed on the page (green = confident, amber = check), field list with confidence, colour-coded PO match, checks, activity timeline with notes, Approve / Reject. Back returns to the screen you came from |
| Upload | Drop a file or pick a test invoice, watch the ten processing steps live, open the result, upload another |
| Vendors, Purchase orders | The master data every invoice is checked against, with live PO balances |
| Settings | The matching rules in force, extraction setup, company profile, demo reset |

## Design

The interface follows the conventions of established AP platforms (Stampli, Tipalti, Ramp, Rossum):
an inbox organised by status, a split review screen with the source document beside the extracted
data, values highlighted on the page, colour-coded PO matching, flags for anomalies, approve/reject
with a recorded reason, and an activity trail per invoice. Hanken Grotesk (SIL Open Font License)
is bundled in `static/fonts`, so the app looks the same offline.

## How it works

```
Upload ─► Document validation ─► Text extraction ─► Structured fields
          (type, size,             (digital text,      (label synonyms,
           signature, opens)        or OCR if scanned)  table headers)
                                                            │
   Decision ◄─ Duplicate check ◄─ Financial checks ◄─ PO match ◄─ Vendor check
      │
      └─► Audit record (run, stages, extracted data, every check, exceptions)
```

Each of the ten stages reports RUNNING → COMPLETED / FAILED as it happens. The
Process page renders these events live and every event is stored.

### Design principles

- **AI reads, rules decide.** Extraction sits behind a provider interface
  (`services/extraction/`). Every financial comparison, tolerance check,
  duplicate rule and the final decision is deterministic Python
  (`decision_engine.py`).
- **Exact money.** All amounts are `Decimal` and are stored as integer paise in SQLite.
- **Like for like.** The invoice's pre-tax value is compared with the PO's
  pre-tax value. Tax is validated separately against the GST rate and type
  (IGST for inter-state supply, CGST + SGST for intra-state).
- **Cumulative PO balance.** Remaining balance = PO value − invoiced before
  InvoiceIQ − invoices approved in InvoiceIQ. This supports split invoicing.
- **Never guess.** Missing fields stay missing. Similar names and descriptions
  are only suggestions. An ambiguous PO is surfaced rather than picked.
- **Root cause first.** When several issues exist, the decision leads with the
  cause (for example, a duplicate) rather than its symptoms (for example, a PO
  that now looks exhausted).

### Tolerance policy (agreed)

Variance % = (cumulative invoiced − PO value) / PO value × 100

| Variance over PO | Outcome |
|---|---|
| ≤ 1% (or the PO's own tolerance) | Pass, with a note |
| > 1% and ≤ 10% | Needs review |
| > 10% | Blocked |

Unit price and quantity must match exactly to pass. Up to 10% over goes to review; more than that is blocked.
Billing *less* than the PO always passes. Settings live in `config/settings.py`.

### Project layout

```
app.py                      Streamlit entrypoint and navigation
config/settings.py          Tolerances, thresholds, paths, buyer profile, LLM env config
data/*.csv                  Synthetic vendor master, PO headers, PO lines
database/db.py              Schema, connection, seeding, reset
database/repository.py      All queries (the only SQL besides db.py)
services/pipeline.py        Orchestrator and live stage events
services/document_processor.py, pdf_extractor.py, ocr_service.py
services/extraction/        Provider interface, rule-based provider, LLM stub
services/invoice_extractor.py   Provider selection and extraction-quality checks
services/vendor_matcher.py, po_matcher.py, financial_validator.py,
services/duplicate_detector.py, tolerance.py, decision_engine.py
ui/                         Pages and shared components
scripts/generate_samples.py   Spec-driven generator for the 14 test invoices
scripts/generate_sample_invoice.py   Earlier single-invoice generator (Dell happy path), superseded by the one above
tests/                      Unit tests and an end-to-end pipeline test
```

---

## Configuration and secrets

No API key is needed. The app reads these optional settings from environment
variables or `.streamlit/secrets.toml` (see `secrets.toml.example`):

| Variable | Purpose |
|---|---|
| `INVOICEIQ_DB_PATH` | SQLite file location (default `var/invoiceiq.db`) |
| `INVOICEIQ_DISPLAY_TZ` | Display timezone (default `Asia/Kolkata`) |
| `INVOICEIQ_TESSERACT_CMD` | Full path to the Tesseract executable, if it is not on PATH |
| `INVOICEIQ_DEMO_PACE_SECONDS` | Pause between stages so viewers can follow the live run (default 0.3; 0 for full speed). Measured durations exclude it. |
| `INVOICEIQ_LLM_PROVIDER`, `INVOICEIQ_LLM_API_KEY`, `INVOICEIQ_LLM_MODEL` | Reserved for an optional LLM extraction provider (not implemented yet) |

The sidebar always shows which extraction provider actually ran.

---

## Deploying to Streamlit Community Cloud

1. Push the repository to GitHub. `var/` and secrets are git-ignored.
2. On share.streamlit.io, create an app from the repository, with main file `app.py` and Python 3.12.
3. `packages.txt` installs Tesseract and `requirements.txt` installs the Python packages.
4. No secrets are required.

Note that Streamlit Cloud storage is ephemeral. The database is re-created and
re-seeded when the app restarts, so processing history does not survive a
restart. All SQL is isolated in `database/` so a managed database can replace
SQLite later.

---

## Data and privacy

All vendors, POs and invoices are synthetic. Uploaded documents are processed
in memory and **are not stored**. Only the file name, size, SHA-256
fingerprint (used for duplicate detection), extracted values and results are kept.
