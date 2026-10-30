# ParchaPay AI synthetic dataset

All records are fictional and for development/demo/testing only. They are not real merchant, GST, lending, or market-price data.

## Files and record counts
- merchants.csv: 30 merchants across Bengaluru PIN codes 560103, 560034, 560095
- suppliers.csv: 8 fictional suppliers
- canonical_skus.csv: 20 products with aliases; embedding is blank intentionally
- mandi_pulse_observations.csv: 480 synthetic benchmark observations (8 per SKU per PIN code)
- invoices.csv: 150 invoices
- invoice_line_items.csv: 502 invoice line items
- gst_ims_records.csv: 150 GST IMS workflow placeholders
- split_credit_loans.csv: 56 simulated credit records
- synthetic_seed.sql: SQL inserts in foreign-key order, compatible with the documented tables

## Load
1. Apply the project's `001_initial_schema.sql` first.
2. Run `synthetic_seed.sql` in Supabase SQL Editor, or import CSVs in this order: merchants, suppliers, canonical_skus, invoices, invoice_line_items, gst_ims_records, split_credit_loans.
3. `mandi_pulse_observations.csv` is an auxiliary file; the current schema has no table for it. Add a table if you want to query those observations directly.
4. Embeddings are blank on purpose. Fake vectors would be meaningless; generate real 768-dimensional embeddings with the model used by your application.
5. Image/audio URLs are placeholders and do not point to actual image/audio files.

## Modeled cases
Line items include price increases vs. benchmark, pen-edited quantities, free units, low OCR confidence (<0.80), GST rates, expiry dates, bounding boxes, and discrepancy reasons. Loan records respect a daily cap of 35% of the merchant's average daily QR volume. Values are synthetic and should not be used for real decisions.

## Caveats
The sample supports UI and pipeline testing, but production-grade reconciliation should recompute invoice totals from line-item-level net amounts, taxes, discounts, and explicit correction rules. GST states are placeholders; no real GST portal integration, payment, lending, settlement, or autopay is performed.
