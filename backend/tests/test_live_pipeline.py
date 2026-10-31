import unittest
from decimal import Decimal
from unittest.mock import AsyncMock, patch

from app.contracts import (
    BoundingBox2D,
    ConfirmCorrectionsRequest,
    ExtractedLineItem,
    LineItemCorrection,
    RawExtractedInvoice,
)
from app.services.credit_rules import CreditPlan
from app.services.pipeline import LiveParchaPipeline, _select_crop_target


MERCHANT_ID = "a0000000-0000-0000-0000-000000000001"
INVOICE_ID = "c0000000-0000-0000-0000-000000000001"


def parsed_invoice():
    return RawExtractedInvoice(
        supplier_name="Sharmaji Wholesale Distributors",
        supplier_gstin="29AABCU9603R1ZM",
        invoice_number="INV-REAL-1",
        invoice_date="2026-10-30",
        printed_grand_total=2948.40,
        line_items=[
            ExtractedLineItem(
                raw_item_name="FORTUNE SUN 1L PO",
                billed_qty=10,
                printed_qty=12,
                free_qty=0,
                unit_rate=134.00,
                gst_percent=5.0,
                line_total=1688.40,
                has_pen_markup=True,
                pen_markup_box=BoundingBox2D(ymin=100, xmin=100, ymax=200, xmax=200),
                confidence_score=0.95,
            ),
            ExtractedLineItem(
                raw_item_name="PARLEG BISCUIT BOX",
                billed_qty=5,
                printed_qty=5,
                free_qty=1,
                unit_rate=240.00,
                gst_percent=5.0,
                line_total=1260.00,
                confidence_score=0.76,
            ),
        ],
    )


def seeded_catalogs():
    suppliers = [
        {
            "id": "supplier-1",
            "name": "Sharmaji Wholesale Distributors",
            "gstin": "29AABCU9603R1ZM",
            "phone": "+910000000000",
        }
    ]
    skus = [
        {
            "id": "sku-oil",
            "product_name": "Fortune Sunlite Refined Sunflower Oil 1L",
            "aliases": ["FORTUNE SUN 1L PO"],
            "standard_mrp": "140.00",
        },
        {
            "id": "sku-biscuit",
            "product_name": "Parle-G Gold Biscuit Box (24pkts)",
            "aliases": ["PARLEG BISCUIT BOX"],
            "standard_mrp": "250.00",
        },
    ]
    return suppliers, skus


def pending_invoice_bundle():
    return {
        "id": INVOICE_ID,
        "merchant_id": MERCHANT_ID,
        "supplier_id": "supplier-1",
        "invoice_number": "INV-REAL-1",
        "invoice_date": "2026-10-30",
        "billed_total": "2948.40",
        "status": "user_pending_review",
        "dispute_crop_url": "/static/crops/pen_edit_test.jpg",
        "suppliers": {
            "name": "Sharmaji Wholesale Distributors",
            "gstin": "29AABCU9603R1ZM",
        },
        "invoice_line_items": [
            {
                "id": "line-1",
                "canonical_sku_id": "sku-oil",
                "raw_item_name": "FORTUNE SUN 1L PO",
                "printed_qty": 12,
                "billed_qty": 10,
                "free_qty": 0,
                "billed_rate": "134.00",
                "tax_percent": "5.00",
                "true_landed_cost": "140.70",
                "mrp": "140.00",
                "has_pen_markup": True,
                "ocr_confidence": "0.950",
            },
            {
                "id": "line-2",
                "canonical_sku_id": "sku-biscuit",
                "raw_item_name": "PARLEG BISCUIT BOX",
                "printed_qty": 5,
                "billed_qty": 5,
                "free_qty": 1,
                "billed_rate": "240.00",
                "tax_percent": "5.00",
                "true_landed_cost": "210.00",
                "mrp": "250.00",
                "has_pen_markup": False,
                "ocr_confidence": "0.760",
            },
        ],
    }


class LivePipelineTests(unittest.IsolatedAsyncioTestCase):
    def test_crop_target_prefers_quantity_edited_marked_row(self):
        box = BoundingBox2D(ymin=100, xmin=100, ymax=200, xmax=200)
        marked_without_quantity_change = ExtractedLineItem(
            raw_item_name="FORTUNE OIL 1L",
            billed_qty=12,
            printed_qty=12,
            unit_rate=100.0,
            line_total=1200.0,
            has_pen_markup=True,
            pen_markup_box=box,
            confidence_score=0.95,
        )
        quantity_edited = ExtractedLineItem(
            raw_item_name="PARLEG BISCUIT BOX",
            billed_qty=10,
            printed_qty=12,
            unit_rate=20.0,
            line_total=200.0,
            has_pen_markup=True,
            pen_markup_box=box,
            confidence_score=0.95,
        )

        self.assertIs(
            _select_crop_target([marked_without_quantity_change, quantity_edited]),
            quantity_edited,
        )

    async def test_scan_persists_pending_draft_without_audit_or_ims(self):
        raw = parsed_invoice()
        suppliers, skus = seeded_catalogs()
        fake_client = object()

        with (
            patch("app.services.pipeline.get_client", new=AsyncMock(return_value=fake_client)),
            patch("app.services.pipeline.extract_invoice_from_image", return_value=raw),
            patch("app.services.pipeline.crop_pen_markup", return_value="/static/crops/pen_edit_test.jpg"),
            patch("app.services.pipeline.repo.get_suppliers", new=AsyncMock(return_value=suppliers)),
            patch("app.services.pipeline.repo.get_canonical_skus", new=AsyncMock(return_value=skus)),
            patch("app.services.pipeline.repo.insert_invoice", new=AsyncMock()) as insert_invoice,
            patch("app.services.pipeline.repo.insert_invoice_line_items", new=AsyncMock()) as insert_lines,
            patch("app.services.pipeline.repo.insert_ims_record", new=AsyncMock()) as insert_ims,
            patch("app.services.pipeline.get_credit_rules") as get_credit_rules,
            patch("app.price_analysis.db.query.get_supplier_history", new=AsyncMock()) as supplier_history,
        ):
            draft = await LiveParchaPipeline().extract_and_draft(
                b"fake-bill-bytes",
                "image/jpeg",
                {"id": MERCHANT_ID, "pincode": "560103", "upi_vpa": "shop@paytm"},
            )

        self.assertEqual(draft.status, "user_pending_review")
        self.assertEqual(draft.merchant_id, MERCHANT_ID)
        self.assertEqual(draft.item_count, 2)
        self.assertEqual(draft.billed_total, 2948.40)
        self.assertEqual(insert_invoice.await_args.args[1]["status"], "user_pending_review")
        rows = insert_lines.await_args.args[1]
        self.assertEqual(rows[0]["canonical_sku_id"], "sku-oil")
        self.assertEqual(rows[0]["true_landed_cost"], "140.70")
        self.assertEqual(rows[0]["bounding_box"], [100, 100, 200, 200])
        self.assertEqual(rows[1]["canonical_sku_id"], "sku-biscuit")
        insert_ims.assert_not_awaited()
        get_credit_rules.assert_not_called()
        supplier_history.assert_not_awaited()

    async def test_confirm_applies_corrections_then_audits_and_verifies(self):
        suppliers, skus = seeded_catalogs()
        bundle = pending_invoice_bundle()
        credit_plan = CreditPlan(
            daily_cap=Decimal("3500.00"),
            max_credit_limit=Decimal("24500.00"),
            is_eligible=True,
            principal=Decimal("2526.30"),
            daily_deduction=Decimal("360.90"),
            remaining_balance=Decimal("2165.40"),
            average_daily_qr_volume=Decimal("10000.00"),
        )
        fake_credit_rules = AsyncMock()
        fake_credit_rules.plan.return_value = credit_plan

        with (
            patch("app.services.pipeline.get_client", new=AsyncMock(return_value=object())),
            patch("app.services.pipeline.repo.get_invoice_bundle", new=AsyncMock(return_value=bundle)) as get_bundle,
            patch(
                "app.services.pipeline.repo.get_merchant",
                new=AsyncMock(return_value={"id": MERCHANT_ID, "pincode": "560103", "upi_vpa": "shop@paytm"}),
            ),
            patch("app.services.pipeline.repo.get_canonical_skus", new=AsyncMock(return_value=skus)),
            patch(
                "app.price_analysis.db.query.get_supplier_history",
                new=AsyncMock(side_effect=[[{"billed_rate": "128.00"}], []]),
            ),
            patch(
                "app.price_analysis.db.query.get_pincode_peer_rates",
                new=AsyncMock(
                    side_effect=[
                        [(f"peer-{i}", str(126 + i)) for i in range(5)],
                        [],
                    ]
                ),
            ),
            patch("app.services.pipeline.get_credit_rules", return_value=fake_credit_rules),
            patch(
                "app.services.pipeline.translate_alert",
                side_effect=lambda text: f"हिंदी: {text}",
            ) as translate_alert,
            patch(
                "app.services.pipeline.synthesize_alert",
                return_value="/static/audio/alert_test.wav",
            ) as synthesize_alert,
            patch("app.services.pipeline.repo.update_invoice_line_item", new=AsyncMock()) as update_line,
            patch("app.services.pipeline.repo.get_ims_record_for_invoice", new=AsyncMock(return_value=None)),
            patch("app.services.pipeline.repo.insert_ims_record", new=AsyncMock()) as insert_ims,
            patch("app.services.pipeline.repo.update_invoice", new=AsyncMock()) as update_invoice,
        ):
            response = await LiveParchaPipeline().confirm_and_audit(
                INVOICE_ID,
                MERCHANT_ID,
                ConfirmCorrectionsRequest(
                    merchant_id=MERCHANT_ID,
                    billed_total=2948.40,
                    corrections=[
                        LineItemCorrection(id="line-1", billed_qty=9),
                    ],
                ),
            )

        get_bundle.assert_awaited_once_with(unittest.mock.ANY, INVOICE_ID, MERCHANT_ID)
        self.assertEqual(response.approved_total, 2526.30)
        self.assertEqual(response.overcharge_amount, 422.10)
        self.assertEqual(response.items[0].billed_qty, 9)
        self.assertEqual(response.items[0].true_landed_cost, 140.70)
        self.assertEqual(response.items[1].discrepancy_type, "LOW_CONFIDENCE_REVIEW")
        self.assertEqual(response.audio_alert_url, "/static/audio/alert_test.wav")
        self.assertTrue(response.voice_transcript.startswith("हिंदी: "))
        self.assertIn("2 lines need review", response.voice_transcript)
        self.assertIn("rupees 2,526", response.voice_transcript)
        self.assertIn("rupees 361", response.voice_transcript)
        self.assertEqual(
            synthesize_alert.call_args_list[0].args,
            (response.voice_transcript, response.invoice_id),
        )
        self.assertEqual(translate_alert.call_count, 1)

        self.assertEqual(update_line.await_count, 2)
        corrected_line = next(
            call.args[2] for call in update_line.await_args_list if call.args[1] == "line-1"
        )
        self.assertEqual(corrected_line["billed_qty"], 9)
        self.assertEqual(corrected_line["true_landed_cost"], "140.70")
        self.assertEqual(update_invoice.await_args.args[2]["status"], "bill_verified")
        self.assertEqual(update_invoice.await_args.args[2]["audio_alert_url"], "/static/audio/alert_test.wav")
        insert_ims.assert_awaited_once()
        self.assertEqual(insert_ims.await_args.args[1]["ims_status"], "PENDING")


if __name__ == "__main__":
    unittest.main()
