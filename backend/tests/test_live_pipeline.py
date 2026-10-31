import unittest
from decimal import Decimal
from unittest.mock import AsyncMock, patch

from app.contracts import BoundingBox2D, ExtractedLineItem, RawExtractedInvoice
from app.services.credit_rules import CreditPlan
from app.services.pipeline import LiveParchaPipeline, _select_crop_target


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

    async def test_decimal_amounts_use_corrected_qty_and_rate_flags_do_not_reprice(self):
        raw = RawExtractedInvoice(
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
        credit_plan = CreditPlan(
            daily_cap=Decimal("3500.00"),
            max_credit_limit=Decimal("24500.00"),
            is_eligible=True,
            principal=Decimal("2667.00"),
            daily_deduction=Decimal("381.00"),
            remaining_balance=Decimal("2286.00"),
            average_daily_qr_volume=Decimal("10000.00"),
        )
        fake_credit_rules = AsyncMock()
        fake_credit_rules.plan.return_value = credit_plan

        with (
            patch("app.services.pipeline.get_client", new=AsyncMock(return_value=object())),
            patch("app.services.pipeline.extract_invoice_from_image", return_value=raw),
            patch("app.services.pipeline.crop_pen_markup", return_value="/static/crops/pen_edit_test.jpg"),
            patch(
                "app.services.pipeline.repo.get_suppliers",
                new=AsyncMock(
                    return_value=[
                        {
                            "id": "supplier-1",
                            "name": "Sharmaji Wholesale Distributors",
                            "gstin": "29AABCU9603R1ZM",
                            "phone": "+910000000000",
                        }
                    ]
                ),
            ),
            patch(
                "app.services.pipeline.repo.get_canonical_skus",
                new=AsyncMock(
                    return_value=[
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
                ),
            ),
            patch(
                "app.price_analysis.db.query.get_supplier_history",
                new=AsyncMock(
                    side_effect=[
                        [{"billed_rate": "128.00"}], [],
                        [{"billed_rate": "128.00"}], [],
                    ]
                ),
            ),
            patch(
                "app.price_analysis.db.query.get_pincode_peer_rates",
                new=AsyncMock(
                    side_effect=[
                        [(f"peer-{i}", str(126 + i)) for i in range(5)],
                        [],
                        [(f"peer-{i}", str(126 + i)) for i in range(5)],
                        [],
                    ]
                ),
            ),
            patch("app.services.pipeline.get_credit_rules", return_value=fake_credit_rules),
            patch(
                "app.services.pipeline.synthesize_alert",
                side_effect=["/static/audio/alert_test.wav", None],
            ) as synthesize_alert,
            patch("app.services.pipeline.repo.insert_invoice", new=AsyncMock()) as insert_invoice,
            patch("app.services.pipeline.repo.insert_invoice_line_items", new=AsyncMock()) as insert_lines,
            patch("app.services.pipeline.repo.insert_ims_record", new=AsyncMock()) as insert_ims,
        ):
            response = await LiveParchaPipeline().extract_and_audit(
                b"fake-bill-bytes",
                "image/jpeg",
                {"id": "merchant-1", "pincode": "560103", "upi_vpa": "shop@paytm"},
            )
            fallback_response = await LiveParchaPipeline().extract_and_audit(
                b"fake-bill-bytes",
                "image/jpeg",
                {"id": "merchant-1", "pincode": "560103", "upi_vpa": "shop@paytm"},
            )

        # The printed grand total is kept for display; line-level math drives
        # approved_total/overcharge, and high rate is flagged rather than
        # silently repriced.
        self.assertEqual(response.billed_total, 2948.40)
        self.assertEqual(response.approved_total, 2667.00)
        self.assertEqual(response.overcharge_amount, 281.40)
        self.assertEqual(response.items[0].billed_rate, 134.00)
        self.assertEqual(response.items[0].true_landed_cost, 140.70)
        self.assertEqual(response.items[0].personal_history_rate, 128.00)
        self.assertEqual(response.items[0].mandi_pulse_median, 128.00)
        self.assertEqual(response.items[1].true_landed_cost, 210.00)
        self.assertEqual(response.items[1].discrepancy_type, "LOW_CONFIDENCE_REVIEW")
        self.assertEqual(response.split_credit_pre_approval.daily_deduction_amount, 381.00)
        self.assertEqual(response.audio_alert_url, "/static/audio/alert_test.wav")
        self.assertIn("2 lines need review", response.voice_transcript)
        self.assertIn("rupees 2,667", response.voice_transcript)
        self.assertIn("rupees 381", response.voice_transcript)
        self.assertLessEqual(response.voice_transcript.count("."), 3)
        self.assertEqual(
            synthesize_alert.call_args_list[0].args,
            (response.voice_transcript, response.invoice_id),
        )
        self.assertEqual(fallback_response.audio_alert_url, "/static/audio/demo_alert.wav")
        self.assertEqual(synthesize_alert.call_count, 2)

        invoice_row = insert_invoice.await_args_list[0].args[1]
        self.assertEqual(invoice_row["approved_total"], "2667.00")
        self.assertEqual(invoice_row["audio_alert_url"], "/static/audio/alert_test.wav")
        self.assertEqual(invoice_row["billed_total"], "2948.40")
        rows = insert_lines.await_args_list[0].args[1]
        self.assertEqual(rows[0]["canonical_sku_id"], "sku-oil")
        self.assertEqual(rows[0]["billed_qty"], 10)
        self.assertEqual(rows[0]["printed_qty"], 12)
        self.assertEqual(rows[0]["mandi_pulse_median"], "128.00")
        self.assertEqual(insert_ims.await_args_list[0].args[1]["ims_status"], "PENDING")


if __name__ == "__main__":
    unittest.main()
