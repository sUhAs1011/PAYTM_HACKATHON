import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from app.api.review_router import get_review, list_pending_reviews


MERCHANT_ID = "a0000000-0000-0000-0000-000000000001"
INVOICE_ID = "c0000000-0000-0000-0000-000000000001"


def draft_bundle(status="user_pending_review"):
    return {
        "id": INVOICE_ID,
        "merchant_id": MERCHANT_ID,
        "supplier_id": "b0000000-0000-0000-0000-000000000001",
        "invoice_number": "INV-TEST-1",
        "invoice_date": "2026-10-30",
        "billed_total": "110.25",
        "status": status,
        "dispute_crop_url": "",
        "suppliers": {"name": "Test Supplier", "gstin": "29AABCU9603R1ZM"},
        "invoice_line_items": [
            {
                "id": "d0000000-0000-0000-0000-000000000001",
                "raw_item_name": "TEST ITEM",
                "printed_qty": 10,
                "billed_qty": 9,
                "free_qty": 1,
                "billed_rate": "10.00",
                "tax_percent": "5.00",
                "true_landed_cost": "9.45",
                "mrp": "12.00",
                "ocr_confidence": "0.950",
                "has_pen_markup": True,
                "bounding_box": [100, 200, 300, 400],
                "canonical_sku_id": "e0000000-0000-0000-0000-000000000001",
            }
        ],
    }


class ReviewApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_pending_queue_returns_only_repo_filtered_merchant_drafts(self):
        with (
            patch("app.api.review_router.get_client", new=AsyncMock(return_value=object())),
            patch(
                "app.api.review_router.repo.get_pending_reviews",
                new=AsyncMock(return_value=[draft_bundle()]),
            ) as query,
        ):
            response = await list_pending_reviews(MERCHANT_ID)

        query.assert_awaited_once()
        self.assertEqual(query.await_args.args[1], MERCHANT_ID)
        self.assertEqual(len(response.drafts), 1)
        self.assertEqual(response.drafts[0].status, "user_pending_review")
        self.assertEqual(response.drafts[0].items[0].billed_qty, 9)
        self.assertEqual(response.drafts[0].items[0].bounding_box, [100, 200, 300, 400])

    async def test_single_review_query_is_scoped_to_merchant(self):
        with (
            patch("app.api.review_router.get_client", new=AsyncMock(return_value=object())),
            patch(
                "app.api.review_router.repo.get_invoice_bundle",
                new=AsyncMock(return_value=draft_bundle()),
            ) as query,
        ):
            response = await get_review(INVOICE_ID, MERCHANT_ID)

        query.assert_awaited_once()
        self.assertEqual(query.await_args.args[1:], (INVOICE_ID, MERCHANT_ID))
        self.assertEqual(response.invoice_id, INVOICE_ID)

    async def test_single_review_rejects_non_pending_invoice(self):
        with (
            patch("app.api.review_router.get_client", new=AsyncMock(return_value=object())),
            patch(
                "app.api.review_router.repo.get_invoice_bundle",
                new=AsyncMock(return_value=draft_bundle(status="bill_verified")),
            ),
        ):
            with self.assertRaises(HTTPException) as raised:
                await get_review(INVOICE_ID, MERCHANT_ID)

        self.assertEqual(raised.exception.status_code, 409)


if __name__ == "__main__":
    unittest.main()
