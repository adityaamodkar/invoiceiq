# Assumptions and design decisions

Reference for the demo and the interview. Each item is a deliberate choice.

## Scope
- **Northwind Components Pvt Ltd** (Telangana, GSTIN 36AAACN5678K1ZZ) is the synthetic company using InvoiceIQ:
  every test invoice is billed to it. Its GSTIN tells the vendor's GSTIN apart from the buyer's on the page, and its
  state decides whether IGST (other state) or CGST + SGST (same state) is correct. It is shown in the sidebar the
  way AP platforms show the active company. Change it in `config/settings.py`.
- InvoiceIQ recommends; it never pays. "Ready for approval" means ready for a human approver.
- The buyer is a single synthetic company, Northwind Components Pvt Ltd (Telangana, GSTIN state 36).
- Currency is INR. A currency mismatch with the PO is blocking.
- All data is synthetic. Uploaded files are not stored; only their SHA-256 fingerprint is kept.

## Extraction
- **The rule-based provider is the default** and needs no API key. It is reliable for the layouts
  we generate; arbitrary vendor layouts would need the LLM provider. This is stated honestly in the UI.
- Header fields are found by label synonyms, never by position alone. The vendor name is the exception:
  it comes from the top of the page, so it gets lower confidence (0.85). Vendor identity is anchored by GSTIN.
- Vendor GSTIN = the GSTIN on the page that is not the buyer's own.
- Confidence is a stated heuristic (label match 0.98, table row 0.97, position 0.85), not a probability.
  For OCR it is multiplied by **Tesseract's own confidence for the words forming that value**, so a clean
  scan can be Ready for approval and a smudged value is sent to review. Below 0.80 on a required field → review.
- Corroboration can stand in for confidence:
  - A line row where qty × rate = amount is rated by its two best-read numbers, because a single misread
    value cannot keep that equation true.
  - A vendor name read with low confidence is accepted only if it exactly matches an approved name or alias.
- Scans and photocopies are cleaned before OCR: copier shadows and scanner borders are trimmed, contrast is
  stretched (grey paper to white, faded toner to dark), skew is corrected (the angle that makes text lines
  sharpest, within ±4°) and specks are removed. If the reading is still weak, a black-and-white (Otsu)
  version is also read and the more confident result kept. Nothing is guessed: a faded copy that can't be
  read confidently goes to review, and a misread GSTIN is caught by its checksum.
- OCR uses Tesseract page-segmentation mode 4 (a single column of variable-size text): it keeps table rows
  intact without merging side-by-side label blocks.
- Currency: if no currency is printed but both parties' GSTINs are present, the invoice is a GST tax invoice
  and therefore in INR. This is shown as inferred, never as printed.
- Missing values stay missing. Missing data → review, never "fraud".

## Matching
- Vendor identity order: GSTIN → legal name or approved alias → fuzzy similarity (suggestion only).
- GSTIN of vendor A with the name of vendor B → blocking (classic misdirected-payment signal).
- An unknown vendor (not in the master) → blocking: unapproved vendors cannot be paid.
- A PO number on the invoice that is not in the system → review (often a typo or misread).
- No PO number: one candidate is *proposed* for confirmation; several are listed as ambiguous. Never auto-picked.
- Line items match on item code, then exact normalized description. Similar descriptions are possible matches only.

## Money
- PO comparison is pre-tax vs pre-tax. Tax is validated separately (rate × taxable value, and IGST vs CGST + SGST from the state codes).
- PO tolerance is measured on the **original PO value** using cumulative invoicing, so every invoice in a split is judged against the same reference.
- Bands: ≤ 1% pass (PO may override), ≤ 10% review, > 10% block. Unit price and quantity: exact to pass, ≤ 10% review, > 10% block. Under-billing passes.
- Only invoices that reach "Ready for approval" consume PO balance; review and blocked ones do not.
- ₹1 rounding allowance on arithmetic checks.

## Duplicates
- Exact (blocking): same file hash, or same vendor + invoice number + total.
- Possible (review): same number with a different total, or same total within 45 days with a different number.
- Exact duplicates are excluded from the dashboard's value total so money is never counted twice.

## Human workflow
- InvoiceIQ's checks produce the starting status (Ready to approve / Needs review / Blocked / Unreadable).
  A person then approves or rejects. Approval means "released for payment in the payment system";
  InvoiceIQ never pays.
- Blocked and unreadable invoices cannot be approved: the cause must be fixed and the invoice processed again.
  Approving an invoice that needs review requires a written reason. Rejecting always requires a reason.
- PO balance is drawn down by an invoice that the checks cleared and nobody rejected, or that a person
  approved after review. (This extends the earlier rule, under which only system-cleared invoices counted.)
- Every approval, rejection and note is kept in the invoice's activity trail with time and user.
- Due date = the printed due date, or invoice date + the vendor's payment terms when none is printed.
- The original document can be shown with highlights during the session that uploaded it (kept in memory
  only, never on disk). Test invoices ship with the app and can always be shown.

## Interface
- Dark mode is a per-installation preference saved in the database (single-user prototype).
- Navigation stays inside the Streamlit session (Back, breadcrumb, sidebar). A plain link or a browser reload starts
  a new session, which would drop the uploaded files held in memory and the Invoices tab/search/sort.
- The invoice page's Back button returns to the screen it was opened from; if that is unknown, to Invoices.
- On a narrow window the invoice list scrolls sideways rather than wrapping each cell: AP lists are scanned by row,
  and wrapped dates and amounts are harder to read than a scroll.
- Purchase orders show money invoiced before InvoiceIQ (opening balance from the PO data) separately from money
  invoiced in InvoiceIQ. All PO amounts are before tax; GST is validated separately and never uses up a PO.

## Operations
- Records can be deleted from the Invoices list or an invoice's More menu (with confirmation). PO balances are computed from history, so
  deleting a run that was Ready for approval returns its amount to the PO. A production AP system would
  archive and keep an immutable audit log instead; deletion exists here to manage demo and test data.
- Test invoices have neutral names and labels; expected outcomes live only in tests and
  `sample_documents/README.md`, so the UI never predicts a result before processing.
- SQLite on Streamlit Cloud is ephemeral; history resets on restart. SQL is isolated in `database/`.
- `INVOICEIQ_DEMO_PACE_SECONDS` (default 0.3 s) pauses between stages so a live audience can follow the run.
  Measured durations exclude it. It is configuration, not a user control.
- The dashboard's "straight-through rate" = invoices Ready for approval ÷ invoices with a decision.
  Exact duplicates are excluded from value totals so money is never counted twice.
