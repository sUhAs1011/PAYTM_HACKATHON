# Soumya — Module 4 Logic

Module 4 validates supplier bills, compares rates against supplier and local peer history, and simulates weekly credit repayments. It uses the shared Supabase client from `backend/app/core/db.py`; it does not create or modify database tables.

## Logging

`backend/app/core/logging_config.py` configures timestamped logs to stdout, reads the optional `LOG_LEVEL` environment variable (defaults to `INFO`), and adds an `X-Request-ID` to API responses. The same request ID appears in logs for the request. Controllers log outcomes and failures, services log workflow milestones, and query modules log table/operation row counts at `DEBUG`. Set `LOG_LEVEL=DEBUG` to see query counts. Logs intentionally omit invoice contents, transaction amounts, phone/VPA values, and credentials.

## Data flow

1. `GET /api/parcha/{invoice_id}/validate` reads `invoices` and `invoice_line_items`. Python `Decimal` recomputes each line's net, GST, line total, and true landed unit cost, then compares the sum with `invoices.billed_total`. The response includes `is_valid` and structured alerts for a total mismatch, stored landed-cost drift, missing lines, or OCR confidence below 0.80. `GET /api/parcha/{invoice_id}/alerts` exposes that alert list directly for the frontend.
2. `GET /api/parcha/{invoice_id}/price-analysis` resolves the invoice's merchant and supplier, then compares each SKU's current billed rate with the median of up to three prior invoices for that merchant and supplier. It also averages same-SKU billed rates from invoices of other merchants in the same pincode over the 14 days up to the invoice date. The peer benchmark activates only when there are at least five distinct peer merchants. Peer IDs and supplier names are not returned.
3. `GET /api/credit/{invoice_id}/recommendation` uses successful incoming transactions (matching the merchant VPA) from the previous 30 days. The principal is the invoice's `billed_total`; the weekly EMI cap is 35% of average weekly QR earnings. A merchant's `avg_daily_qr_volume` is used only when the transaction history yields no successful earnings, and the response identifies that fallback.
4. `POST /api/credit/{invoice_id}/accept` requires `{"mandate_accepted": true}` and creates a simulated loan plus a `LOAN_DISBURSEMENT_SIMULATED` ledger entry. `POST /api/credit/loans/{loan_id}/simulate-week` applies successful incoming QR receipts from successive non-overlapping historical seven-day windows (anchored at loan creation) against the weekly installment, updates the loan balance, and records one paid, missed, or partial ledger event per simulated week. The live ledger has a unique constraint allowing only one entry per loan per India-local calendar day; weekly events are stamped at the simulated installment date to respect it. Partial-event kind records both the paid amount (`amount`) and missed amount (kind suffix). This makes the flow demoable from existing transaction history; it is not a live settlement sweep. Missed amounts are alert records, not real autopay or bank debits. `GET .../schedule` and `GET .../alerts` expose the schedule and missed-payment alerts.

## Existing database contracts used

- `invoices`: `id`, `merchant_id`, `supplier_id`, `invoice_date`, `billed_total` and the other existing CIS fields.
- `invoice_line_items`: `invoice_id`, `canonical_sku_id`, `raw_item_name`, `billed_qty`, `free_qty`, `billed_rate`, `tax_percent`, `true_landed_cost`, `mrp`, and the other CIS fields. This table links the invoice to the bill's SKU-level details; the `transactions` table has no `invoice_id` or SKU key in the supplied schema.
- `merchants`: `id`, `pincode`, `upi_vpa`, `avg_daily_qr_volume`.
- `suppliers`: `id` and supplier details; invoice supplier matching uses `invoices.supplier_id`.
- `transactions`: `t_id`, `merchant_id`, `amount`, `payer_vpa`, `merchant_vpa`, `txn_ref`, `txn_status`, `upi_partner`, `created_at`, plus the bill-related fields shown in the supplied schema. Credit calculations use successful incoming transaction amounts and timestamps.
- `split_credit_loans`: existing CIS columns only. Weekly tenure is represented as `tenure_days = tenure_weeks × 7`; `daily_cap_limit` and `daily_deduction_rate` are compatibility projections. Weekly EMI values are deterministically reconstructed from `principal_amount` and `tenure_days`, with the final installment absorbing the rounding remainder. The weekly schedule/alerts endpoints require the simulated-disbursement ledger marker so legacy daily CIS loans are not misread as weekly loans.
- `merchant_account_ledger`: `id`, `merchant_id`, `entry_ts`, `kind`, `amount`, `loan_id`, `created_at`. The loan row remains the source of `remaining_balance`; ledger `kind` distinguishes simulated disbursement, paid EMI, and missed EMI alert events.

Table and column use is based on the CIS in `documents/engineering_document_core_interoperability_specification-2.md` and the Supabase schema screenshots supplied for Module 4. If the live schema differs, the query layer should fail clearly; do not add or alter schema without approval.

## Routes

| Method | Route | Purpose |
| --- | --- | --- |
| GET | `/api/parcha/{invoice_id}/validate` | Recompute bill math and GST; return line calculations and alerts. |
| GET | `/api/parcha/{invoice_id}/alerts` | Return frontend-consumable validation alerts. |
| GET | `/api/parcha/{invoice_id}/price-analysis` | Return same-supplier history and gated pincode peer averages. |
| GET | `/api/credit/{invoice_id}/recommendation` | Calculate eligibility, weekly cap, tenure, and EMI schedule. |
| POST | `/api/credit/{invoice_id}/accept` | Simulate accepting a mandate and creating a loan. |
| GET | `/api/credit/loans/{loan_id}/schedule` | Return schedule, balance, and ledger records. |
| POST | `/api/credit/loans/{loan_id}/simulate-week` | Simulate a weekly QR sweep and report any missed amount. |
| GET | `/api/credit/loans/{loan_id}/alerts` | Return persisted missed-installment alerts. |

## Verification

From `backend/`, run:

```sh
python -m unittest discover -s tests -v
```

Start the API from `backend/` with:

```sh
uvicorn app.main:app --env-file ../.env --host 0.0.0.0 --port 8000
```

Live routes require the root `.env` containing `SUPABASE_URL` and `SUPABASE_SECRET_KEY`. Never commit that file or send credentials through chat.
