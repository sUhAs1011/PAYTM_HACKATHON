"""One-shot live smoke test for the human-in-the-loop review APIs.

Exercises: POST /api/parcha/scan (draft), GET pending-review, GET review,
POST confirm (corrections -> audit -> bill_verified), plus error paths and
before/after Supabase row counts. Creates real invoice/line/IMS rows --
prints their IDs for cleanup review. No rows are deleted by this script.

Run from backend/:  python run_review_flow_smoke.py
"""

import asyncio
import json
from pathlib import Path

import httpx

from app.core import repo
from app.core.db import get_client
from app.core.ws_manager import WebSocketManager
from app.main import app
from app.services.credit_rules import LiveCreditRules, set_credit_rules
from app.services.pipeline import LiveParchaPipeline, set_pipeline

MARKED_IMAGE = Path("tests/test_images/736b7d7e-64d8-491d-9ea8-59ec3d08ca5b.png")
VALID_UUID = "00000000-0000-0000-0000-000000000001"

results = []


def record(step, status, detail=""):
    results.append((step, status, detail))
    print(f"[{status:>4}] {step} -- {detail}")


async def table_counts(client):
    counts = {}
    for table in ("invoices", "invoice_line_items", "gst_ims_records"):
        response = await client.table(table).select("id", count="exact").limit(1).execute()
        counts[table] = response.count
    return counts


async def seed_fallback_draft(client):
    """If Gemini is unavailable, write the same draft shape scan persists so
    the review/confirm legs can still be tested end-to-end."""
    import uuid
    merchant = await repo.first_merchant_with_invoice(client)
    invoice_id = str(uuid.uuid4())
    await repo.insert_invoice(client, {
        "id": invoice_id,
        "merchant_id": merchant["id"],
        "supplier_id": None,
        "invoice_number": "INV-REVIEW-SMOKE-1",
        "invoice_date": "2026-10-31",
        "billed_total": "250.00",
        "approved_total": "220.50",
        "overcharge_amount": "0.00",
        "status": "user_pending_review",
    })
    await repo.insert_invoice_line_items(client, [
        {
            "invoice_id": invoice_id,
            "canonical_sku_id": None,
            "raw_item_name": "SMOKE ITEM A",
            "printed_qty": 10,
            "billed_qty": 10,
            "free_qty": 0,
            "billed_rate": "20.00",
            "tax_percent": "5.00",
            "true_landed_cost": "21.00",
            "has_pen_markup": False,
            "ocr_confidence": "0.950",
        },
        {
            "invoice_id": invoice_id,
            "canonical_sku_id": None,
            "raw_item_name": "SMOKE ITEM B",
            "printed_qty": 2,
            "billed_qty": 2,
            "free_qty": 0,
            "billed_rate": "10.00",
            "tax_percent": "5.00",
            "true_landed_cost": "10.50",
            "has_pen_markup": False,
            "ocr_confidence": "0.900",
        },
    ])
    return invoice_id, merchant["id"], ["", ""]


async def main():
    # Mirror app lifespan so the pipeline/WS seams exist outside Uvicorn.
    app.state.ws_manager = WebSocketManager()
    set_pipeline(LiveParchaPipeline())
    set_credit_rules(LiveCreditRules())

    client = await get_client()
    before = await table_counts(client)
    print("Baseline counts:", before)

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test", timeout=120
    ) as http:

        # --- 1. POST /api/parcha/scan ---
        image_bytes = MARKED_IMAGE.read_bytes()
        scan = await http.post(
            "/api/parcha/scan",
            files={"file": ("bill.png", image_bytes, "image/png")},
            data={"merchant_id": ""},
        )
        draft_id = merchant_id = None
        if scan.status_code == 200:
            body = scan.json()
            draft_id = body["invoice_id"]
            merchant_id = body["merchant_id"]
            record("POST /scan -> draft", "PASS",
                   f"status={body['status']} items={body['item_count']} invoice={draft_id}")
        else:
            record("POST /scan -> draft", "FAIL", f"{scan.status_code}: {scan.text[:200]}")
            record("fallback draft seed", "INFO", "seeding draft directly for downstream tests")
            draft_id, merchant_id, _ = await seed_fallback_draft(client)

        # --- 2. GET pending-review queue ---
        queue = await http.get("/api/parcha/pending-review", params={"merchant_id": merchant_id})
        queued = any(d["invoice_id"] == draft_id for d in queue.json().get("drafts", [])) if queue.status_code == 200 else False
        record("GET /pending-review", "PASS" if queue.status_code == 200 and queued else "FAIL",
               f"{queue.status_code}, drafts={len(queue.json().get('drafts', []))}, contains_new={queued}")

        # --- 3. GET single draft ---
        review = await http.get(f"/api/parcha/{draft_id}/review", params={"merchant_id": merchant_id})
        items = review.json().get("items", []) if review.status_code == 200 else []
        record("GET /{id}/review", "PASS" if review.status_code == 200 and items else "FAIL",
               f"{review.status_code}, items={len(items)}")
        first_item_id = items[0]["id"] if items else None

        # --- 4. POST confirm with a correction ---
        confirm_body = {
            "merchant_id": merchant_id,
            "invoice_number": "INV-CONFIRMED-001",
            "corrections": (
                [{"id": first_item_id, "billed_qty": items[0]["billed_qty"] + 1,
                  "raw_item_name": "CORRECTED NAME"}]
                if first_item_id else []
            ),
        }
        confirm = await http.post(f"/api/parcha/{draft_id}/confirm", json=confirm_body)
        record("POST /{id}/confirm", "PASS" if confirm.status_code == 200 else "FAIL",
               f"{confirm.status_code}" + (
                   f" approved={confirm.json().get('approved_total')} overcharge={confirm.json().get('overcharge_amount')}"
                   if confirm.status_code == 200 else f" {confirm.text[:200]}"))

        # --- 5. Post-confirm states ---
        re_review = await http.get(f"/api/parcha/{draft_id}/review", params={"merchant_id": merchant_id})
        record("GET /{id}/review after confirm", "PASS" if re_review.status_code == 409 else "FAIL",
               f"{re_review.status_code} (expect 409)")
        queue2 = await http.get("/api/parcha/pending-review", params={"merchant_id": merchant_id})
        still_queued = any(d["invoice_id"] == draft_id for d in queue2.json().get("drafts", [])) if queue2.status_code == 200 else True
        record("GET /pending-review after confirm", "PASS" if queue2.status_code == 200 and not still_queued else "FAIL",
               f"{queue2.status_code}, still_queued={still_queued}")
        confirm_again = await http.post(f"/api/parcha/{draft_id}/confirm", json={"merchant_id": merchant_id})
        record("POST /{id}/confirm again", "PASS" if confirm_again.status_code == 409 else "FAIL",
               f"{confirm_again.status_code} (expect 409)")

        # --- 6. Error paths ---
        bad_pending = await http.get("/api/parcha/pending-review", params={"merchant_id": "not-a-uuid"})
        record("pending-review bad merchant UUID", "PASS" if bad_pending.status_code == 422 else "FAIL", str(bad_pending.status_code))
        missing_merchant = await http.get("/api/parcha/pending-review")
        record("pending-review missing merchant_id", "PASS" if missing_merchant.status_code == 422 else "FAIL", str(missing_merchant.status_code))
        bad_invoice = await http.get(f"/api/parcha/not-a-uuid/review", params={"merchant_id": merchant_id})
        record("review bad invoice UUID", "PASS" if bad_invoice.status_code == 422 else "FAIL", str(bad_invoice.status_code))
        missing = await http.get(f"/api/parcha/{VALID_UUID}/review", params={"merchant_id": merchant_id})
        record("review nonexistent invoice", "PASS" if missing.status_code == 404 else "FAIL", str(missing.status_code))
        wrong_merchant = await http.get(
            f"/api/parcha/{draft_id}/review", params={"merchant_id": VALID_UUID})
        record("review wrong merchant", "PASS" if wrong_merchant.status_code == 404 else "FAIL", str(wrong_merchant.status_code))
        bad_item = await http.post(f"/api/parcha/{VALID_UUID}/confirm", json={
            "merchant_id": merchant_id,
            "corrections": [{"id": "line-does-not-exist", "billed_qty": 1}],
        })
        record("confirm nonexistent invoice", "PASS" if bad_item.status_code == 404 else "FAIL", str(bad_item.status_code))

    # --- 7. DB state verification ---
    bundle = await repo.get_invoice_bundle(client, draft_id)
    status = bundle.get("status") if bundle else "MISSING"
    record("DB invoice status", "PASS" if status == "bill_verified" else "FAIL", status)
    ims = await repo.get_ims_record_for_invoice(client, draft_id)
    record("DB IMS row exists", "PASS" if ims else "FAIL", f"ims_status={ims.get('ims_status') if ims else None}")
    corrected = next(
        (i for i in (bundle.get("invoice_line_items") or []) if i["raw_item_name"] == "CORRECTED NAME"),
        None,
    ) if bundle else None
    record("DB line correction persisted", "PASS" if corrected else "FAIL",
           f"raw_item_name={corrected['raw_item_name'] if corrected else 'unchanged'}")

    after = await table_counts(client)
    print("\nCounts before:", before, "-> after:", after)

    print("\n===== SUMMARY =====")
    for step, status, detail in results:
        print(f"{status:>4} | {step} | {detail}")
    print(f"\nTest invoice left in DB for review: {draft_id} (status={status})")


if __name__ == "__main__":
    asyncio.run(main())
