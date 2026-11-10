# Test invoices

Regenerate with `python scripts/generate_samples.py`. All data is synthetic and agrees with `data/*.csv`.
File names are neutral so the app never hints at an outcome. **This table is for demo preparation only.**

The set is a **sequence**: some outcomes depend on what was processed before (a re-sent duplicate needs the
original; the third split invoice needs the first two). **Process all 14** in Upload runs them in this order.
Start from a clean state (Settings, then Reset demo data).

| # | File | Expected | What it shows |
|---|---|---|---|
| 1 | `dell_inv_00418.pdf` | Ready for approval | Clean digital PDF, ruled table, item codes, IGST. |
| 2 | `hp_inv_77031.pdf` | Ready for approval | Title above vendor name; 'Invoice Number' / bare 'Date' / 'Purchase Order No.'; INR 590,000.00 format; unit EA. |
| 3 | `deccan_bill_1187.pdf` | Ready for approval | Local trader: unruled columns, 'Bill No.', no item codes, 'Rs. ... /-', CGST + SGST. |
| 4 | `sigma_inv_0932_scan.pdf` | Ready for approval | Clean scanned PDF (OCR); no currency printed; partial delivery (120 of 200 reams). |
| 5 | `hp_inv_77104.pdf` | Needs review | Unit price +4% over PO and PO value +2%: inside the 10% review band. |
| 6 | `abc_inv_0571_photo.jpg` | Blocked | Phone photo from a vendor whose record is Inactive. |
| 7 | `hp_inv_77188.pdf` | Ready for approval | Split invoicing 1/3: 18 of 30 monitors on PO-2026-0008. |
| 8 | `hp_inv_77245.pdf` | Ready for approval | Split invoicing 2/3: the other 12 monitors; PO-2026-0008 is now fully invoiced. |
| 9 | `hp_inv_77302.pdf` | Blocked | Split invoicing 3/3: 4 more monitors after all 30 were billed; nothing left on the PO. |
| 10 | `dell_inv_00418_resent_photocopy.pdf` | Blocked | The vendor re-sent invoice 00418 as a photocopy: a different file, caught by vendor + invoice number + amount. |
| 11 | `sigma_inv_0987_photocopy.pdf` | Ready for approval | Grey, skewed photocopy with specks and a copier shadow; bills the last 80 reams of PO-2026-0005. |
| 12 | `deccan_bill_1203.pdf` | Needs review | No PO number on the bill: the vendor's open PO is proposed, never picked automatically. |
| 13 | `orbit_inv_2231.pdf` | Blocked | Vendor not in the vendor master (never onboarded). |
| 14 | `deccan_bill_1219_faded_copy.jpg` | Needs review | Badly faded photocopy: OCR misreads a GSTIN character (caught by the checksum) and cannot read several fields. |

Scanned PDFs, photocopies and photos need Tesseract. Photocopies are cleaned before OCR: dark edges trimmed,
contrast stretched, skew corrected, specks removed; a black-and-white version is also tried and the more
confident reading kept.
