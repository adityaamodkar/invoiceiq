# Project status

_Last updated: 10 Nov 2026_

## Done

| Area | Evidence |
|---|---|
| Upload validation (type, size, signature, corrupt/encrypted) | `test_extraction.py` |
| Digital PDF extraction (pdfplumber) and OCR (Tesseract, psm 4) for scans, photocopies and photos | 14-invoice test set |
| Rule-based extraction across vendor variations (labels, number formats, units, tax styles, table styles) | `test_vendor_variations.py` |
| Measured OCR confidence per field; corroboration rules (row arithmetic, exact vendor match) | Scanned and photocopied samples are Ready; low-confidence values go to review |
| OCR clean-up for photocopies (edge trim, contrast, deskew, despeckle, Otsu fallback) | `sigma_inv_0987_photocopy.pdf` is Ready |
| Vendor, PO, line-item, financial, duplicate checks; deterministic decision engine | `test_business_logic.py` |
| Edge cases: split invoicing, re-sent duplicate, inactive and unknown vendor, missing PO, faded copy with a misread GSTIN | Sequential sample-set tests; browser-verified |
| Audit trail: runs, stage events, extracted data, every check, exceptions | `test_pipeline_e2e.py` |
| Human workflow: approve (reason required when under review), reject (reason required), notes, bulk approve / reject / delete, activity trail | `test_workflow.py`, browser-verified |
| UI modelled on AP platforms: inbox with status tabs, split review screen with field highlights, colour-coded PO match, flags, due dates | Browser-verified, light and dark |
| Deployment files | requirements.txt, packages.txt (Tesseract), .gitignore, secrets example |

**Tests:** 104 passing (`python -m pytest -q`). OCR tests skip automatically if Tesseract is not installed.

## Test set results (verified 10 Nov 2026, processed in order with "Process all 14")

| # | Invoice | Result |
|---|---|---|
| 1 | dell_inv_00418.pdf | Ready to approve |
| 2 | hp_inv_77031.pdf | Ready to approve |
| 3 | deccan_bill_1187.pdf | Ready to approve |
| 4 | sigma_inv_0932_scan.pdf | Ready to approve |
| 5 | hp_inv_77104.pdf | Needs review (price variance, over PO value) |
| 6 | abc_inv_0571_photo.jpg | Blocked (inactive vendor) |
| 7 | hp_inv_77188.pdf | Ready to approve |
| 8 | hp_inv_77245.pdf | Ready to approve |
| 9 | hp_inv_77302.pdf | Blocked (quantity over PO, over PO value) |
| 10 | dell_inv_00418_resent_photocopy.pdf | Blocked (duplicate) |
| 11 | sigma_inv_0987_photocopy.pdf | Ready to approve |
| 12 | deccan_bill_1203.pdf | Needs review (PO not matched) |
| 13 | orbit_inv_2231.pdf | Blocked (vendor not approved) |
| 14 | deccan_bill_1219_faded_copy.jpg | Needs review (vendor unclear, GSTIN invalid, …) |

Totals: 7 Ready, 3 Needs review, 4 Blocked; touchless rate 50%.

## UI pass, 10 Nov 2026

All items below were checked in a real browser (in-app Chromium, 1024 and 1440 px wide) in light and dark mode,
against a scratch database so `var/invoiceiq.db` was not touched.

**Sidebar**
- A collapsed sidebar can be reopened. Streamlit's top bar holds the expand control, so it is no longer hidden;
  only its menu, deploy button, status widget and header logo are. The fixed sidebar width now applies only while
  the sidebar is open (it used to leave an empty 244 px gutter after collapsing).
- One grid, measured with getBoundingClientRect: logo, nav icons, group labels, company text and the Dark mode
  switch share one left edge; the Upload button and row highlights share a second one. Group labels no longer overlap
  the row below. The count badge is right-aligned. Width 17.5rem so the company name fits on one line.
- The Dark mode switch is visible when off (its knob had the sidebar's own colour).

**Navigation**
- Invoice page: "Back to Home / Invoices / Upload" returns to where you came from (tracked in session state, falls
  back to Invoices). The breadcrumb now navigates inside the session; the old link reloaded the page and lost state.
- Invoices keeps its status tab, search and sort when you come back.
- Upload: "Upload another" after a result; picking a test invoice is no longer overridden by a file still in the uploader.
- Every dialog has Cancel. The More menu closes before the delete confirmation opens (it used to stay on top of it,
  and the Delete click could be lost). Reject now names the invoice like Approve and Delete do.

**Audit fixes**
- Page titles no longer touch the content below (Streamlit's −1rem margin on markdown blocks).
- Header actions are right-aligned and level with the title, sized to their label.
- KPI row reflows (5 across, then 3 over 2); side-by-side sections stack below 1240 px.
- The invoice list scrolls sideways on narrow windows instead of wrapping dates, PO numbers and amounts.
- Tables line up with their card heading and scroll inside the card; PO match "Lines" fits by showing the PO price
  under the invoice price; Settings rule columns no longer wrap.
- Approve / Reject / More are never clipped.
- Visible keyboard focus; text boxes, dropdowns, checkboxes and dialogs styled for Streamlit 1.66 in both modes
  (dialogs had the default font and a light scrim in dark mode).
- Empty states for Vendors (no search match) and Purchase orders (no PO with a status), outside the card.
- Volume chart: at most about six y-axis ticks. "Reset demo data" refreshes the sidebar count and unticks its confirmation.

**Known limits**
- Below roughly 1200 px wide (for example a 1024 px window with the sidebar open) the invoice list needs a sideways
  scroll to reach Status and Flags. Collapsing the sidebar or a wider window shows every column.
- Open question: "Due in the next 14 days" on Home lists blocked exact duplicates as due (the re-sent Dell invoice
  appears twice). Left unchanged pending a decision.

## Next (awaiting instruction)

1. Reviewer correction and re-run screen (`parent_run_id` and `review_actions` already in the schema).
2. Deployment to Streamlit Community Cloud (needs your repository confirmation).
3. Optional LLM extraction provider (needs your choice of provider).
4. Demo script and interview preparation.
