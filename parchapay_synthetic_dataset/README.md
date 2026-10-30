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
- transactions.csv: 7,233 synthetic UPI QR payments (2026-10-01 to 2026-10-30). Per merchant, SUCCESS-amounts sum to exactly 30 x merchants.avg_daily_qr_volume, so a computed 30-day average always matches the stored column. Requires the transactions table (full merchant payment rail: amount, payer_vpa, merchant_vpa, txn_ref, txn_status, upi_partner) to exist first; seed SQL inserts data only.
- merchant_account_ledger.csv: 175 rows (30 OPENING + 145 LOAN_DEDUCT). Deductions reconcile to split_credit_loans.remaining_balance for 54/56 loans; 2 loans created Oct 28 carry only the deductions that fit Oct 1..30 under the once-per-day rule. QR_CREDIT rows are intentionally absent - credits derive from the transactions table.
- synthetic_seed_ledger.sql: SQL inserts for merchant_account_ledger in foreign-key order, compatible with the documented tables
- synthetic_seed_transactions_1.sql..4.sql: transactions inserts split to fit the SQL Editor per-query size limit

## Load

The full seed is ~1.9 MB and exceeds the Supabase SQL Editor's per-query size limit, so it is split:

1. Apply the project's `001_initial_schema.sql` first (creates the 7 CIS tables).
2. Run `synthetic_seed.sql` in Supabase SQL Editor (merchants, suppliers, canonical_skus, invoices, invoice_line_items, gst_ims_records, split_credit_loans). Idempotent via ON CONFLICT.
3. Create the `transactions` table with its own DDL first (data is not included in any seed file).
4. Run `synthetic_seed_transactions_1.sql` through `synthetic_seed_transactions_4.sql` — four ~368 KB files (≈1,800 rows each). Order does not matter; re-running is safe.
5. Choose the Mandi-Pulse source before Module 4: invoice history (spec-pure) or load `mandi_pulse_observations.csv` into an auxiliary table (deviation, needs approval).
6. `canonical_skus.embedding` is blank by design; generate real 768-dim embeddings with the runtime model before the pgvector cosine search demo.
7. Image/audio URLs under `/static/synthetic/...` are placeholders; no real files exist behind them.

## Modeled cases
Line items include price increases vs. benchmark, pen-edited quantities, free units, low OCR confidence (<0.80), GST rates, expiry dates, bounding boxes, and discrepancy reasons. Loan records respect a daily cap of 35% of the merchant's average daily QR volume. Values are synthetic and should not be used for real decisions.

## Caveats
The sample supports UI and pipeline testing, but production-grade reconciliation should recompute invoice totals from line-item-level net amounts, taxes, discounts, and explicit correction rules. GST states are placeholders; no real GST portal integration, payment, lending, settlement, or autopay is performed.
