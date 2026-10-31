"""Scan pipeline seam: draft extraction + confirmed audit.

The golden fixture remains isolated to `/api/demo/load-sample`. Uploaded
scans run Gemini extraction and Pillow crop, then persist the raw parse as
`invoices.status='user_pending_review'` for the human-in-the-loop review.
Only after the merchant confirms corrections does the deterministic audit
(line checks, price analysis, QR-credit pre-approval) run; the invoice then
flips to `bill_verified`, the IMS row is inserted, and AUDIT_COMPLETE is
broadcast by the router.
"""

import asyncio
import logging
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Protocol
from uuid import uuid4

from starlette.concurrency import run_in_threadpool

from app.contracts import (
    AuditedInvoiceResponse,
    AuditedItem,
    ConfirmCorrectionsRequest,
    GstImsShield,
    ScanDraftResponse,
    SplitCreditPreApproval,
)
from app.core import repo
from app.core.config import fixture_candidates, get_settings
from app.core.db import get_client
from app.core.money import as_float, dec, q2
from app.services.credit_rules import get_credit_rules
from app.services.gemini_vision import extract_invoice_from_image
from app.services.pillow_cropper import crop_pen_markup

logger = logging.getLogger("parchapay.api.pipeline")


class DraftNotFoundError(Exception):
    """The requested review invoice does not exist."""


class DraftConflictError(Exception):
    """The invoice exists but is not awaiting review (already verified/other)."""


class ParchaPipeline(Protocol):
    async def extract_and_draft(
        self, image_bytes: bytes, content_type: str, merchant: dict
    ) -> ScanDraftResponse:  # pragma: no cover - interface
        ...

    async def confirm_and_audit(
        self, invoice_id: str, merchant_id: str, request: ConfirmCorrectionsRequest
    ) -> AuditedInvoiceResponse:  # pragma: no cover - interface
        ...


_pipeline: Optional[ParchaPipeline] = None


def set_pipeline(implementation: ParchaPipeline) -> None:
    global _pipeline
    _pipeline = implementation
    logger.info("ParchaPipeline seam set: %s", type(implementation).__name__)


def get_pipeline() -> ParchaPipeline:
    if _pipeline is None:
        raise RuntimeError("Pipeline not initialized")
    return _pipeline


class FixturePipeline:
    """Golden fixture adapter, used only by the explicit demo endpoint."""

    def __init__(self) -> None:
        self._response: Optional[AuditedInvoiceResponse] = None

    def load(self) -> AuditedInvoiceResponse:
        if self._response is None:
            last_error: Optional[Exception] = None
            for path in fixture_candidates():
                try:
                    import json

                    raw = json.loads(path.read_text(encoding="utf-8-sig"))
                    self._response = AuditedInvoiceResponse.model_validate(raw)
                    logger.info("golden demo fixture loaded")
                    break
                except Exception as exc:
                    last_error = exc
            if self._response is None:
                raise RuntimeError(f"golden fixture unavailable: {last_error}")
        return self._response


class LiveParchaPipeline:
    """Real scan path. No demo-specific quantity rewriting or fake SKU IDs."""

    async def extract_and_draft(
        self, image_bytes: bytes, content_type: str, merchant: dict
    ) -> ScanDraftResponse:
        """Gemini extraction → supplier/SKU match → pen-edit crop → persist a
        user_pending_review draft. No audit, IMS row, or credit math yet."""
        from app.engine.math_engine import calculate_line

        client = await get_client()
        extracted = await run_in_threadpool(
            extract_invoice_from_image, image_bytes, mime_type=content_type
        )
        if not extracted.line_items:
            raise ValueError("The bill contains no extractable line items")

        invoice_id = str(uuid4())
        invoice_date = _invoice_date(extracted.invoice_date)
        suppliers, skus = await asyncio.gather(
            repo.get_suppliers(client),
            repo.get_canonical_skus(client),
        )
        supplier = _match_supplier(extracted.supplier_name, extracted.supplier_gstin, suppliers)
        sku_matches = [_match_sku(item.raw_item_name, skus) for item in extracted.line_items]

        # Crop only an OCR-confirmed box; never fabricate a box/crop for demo quantities.
        #identified one source of problem
        crop_target = next(
            (
                item
                for item in extracted.line_items
                if item.has_pen_markup and item.pen_markup_box is not None
            ),
            None,
        )
        crop_url = ""
        if crop_target is not None:
            crop_url = await run_in_threadpool(
                crop_pen_markup, image_bytes, crop_target.pen_markup_box, invoice_id
            )

        stored_items: list[dict] = []
        provisional_total = Decimal("0.00")
        for raw_item, sku in zip(extracted.line_items, sku_matches):
            line_calc = calculate_line(
                {
                    "raw_item_name": raw_item.raw_item_name,
                    "billed_qty": raw_item.billed_qty,
                    "free_qty": raw_item.free_qty,
                    "billed_rate": raw_item.unit_rate,
                    "tax_percent": raw_item.gst_percent,
                    "ocr_confidence": raw_item.confidence_score,
                }
            )
            provisional_total += line_calc.expected_line_total
            has_pen_markup = bool(
                raw_item.has_pen_markup or raw_item.printed_qty != raw_item.billed_qty
            )
            stored_items.append(
                {
                    "invoice_id": invoice_id,
                    "canonical_sku_id": sku["id"] if sku else None,
                    "raw_item_name": raw_item.raw_item_name,
                    "printed_qty": raw_item.printed_qty,
                    "billed_qty": raw_item.billed_qty,
                    "free_qty": raw_item.free_qty,
                    "billed_rate": str(q2(dec(raw_item.unit_rate))),
                    "tax_percent": str(q2(dec(raw_item.gst_percent))),
                    "true_landed_cost": str(line_calc.true_landed_cost),
                    "mrp": str(q2(dec(raw_item.mrp))) if raw_item.mrp is not None else None,
                    "has_pen_markup": has_pen_markup,
                    "ocr_confidence": str(dec(raw_item.confidence_score)),
                    "bounding_box": _box_array(raw_item.pen_markup_box),
                    "discrepancy_reason": None,
                    "mandi_pulse_median": None,
                }
            )

        billed_total = q2(dec(extracted.printed_grand_total))
        invoice_number = extracted.invoice_number or f"INV-{invoice_date.year}-{uuid4().hex[:6].upper()}"
        invoice_row = {
            "id": invoice_id,
            "merchant_id": merchant["id"],
            "supplier_id": supplier["id"] if supplier else None,
            "invoice_number": invoice_number,
            "invoice_date": invoice_date.isoformat(),
            "raw_image_url": None,
            "dispute_crop_url": crop_url or None,
            "audio_alert_url": None,
            "billed_total": str(billed_total),
            "approved_total": str(q2(provisional_total)),
            "overcharge_amount": "0.00",
            "status": repo.INVOICE_STATUS_USER_PENDING_REVIEW,
        }
        await self._persist_draft(client, invoice_row, stored_items)
        logger.info(
            "scan draft persisted invoice_id=%s merchant_id=%s item_count=%d",
            invoice_id,
            merchant["id"],
            len(stored_items),
        )
        return ScanDraftResponse(
            invoice_id=invoice_id,
            status=repo.INVOICE_STATUS_USER_PENDING_REVIEW,
            supplier_name=extracted.supplier_name,
            supplier_gstin=extracted.supplier_gstin or "",
            invoice_number=invoice_number,
            invoice_date=invoice_date.isoformat(),
            billed_total=as_float(billed_total),
            item_count=len(stored_items),
            dispute_crop_url=crop_url,
            merchant_id=str(merchant["id"]),
        )

    async def confirm_and_audit(
        self, invoice_id: str, merchant_id: str, request: ConfirmCorrectionsRequest
    ) -> AuditedInvoiceResponse:
        """Apply merchant corrections to a pending draft, then run the full
        deterministic audit on the corrected data and flip bill_verified."""
        from app.engine.math_engine import calculate_line
        from app.engine.waterfall_engine import analyze_price
        from app.price_analysis.db.query import get_pincode_peer_rates, get_supplier_history

        client = await get_client()
        bundle = await repo.get_invoice_bundle(client, invoice_id, merchant_id)
        if bundle is None:
            raise DraftNotFoundError(f"invoice {invoice_id} not found")
        if bundle.get("status") != repo.INVOICE_STATUS_USER_PENDING_REVIEW:
            raise DraftConflictError(
                f"invoice status {bundle.get('status')!r} is not awaiting review"
            )
        merchant = await repo.get_merchant(client, str(bundle["merchant_id"]))
        if merchant is None:
            raise RuntimeError("invoice merchant could not be resolved")

        rows = {
            str(item["id"]): dict(item)
            for item in (bundle.get("invoice_line_items") or [])
        }
        if not rows:
            raise DraftConflictError("draft invoice has no line items to confirm")

        correction_ids = [correction.id for correction in request.corrections]
        if len(correction_ids) != len(set(correction_ids)):
            raise ValueError("each line item may only be corrected once per request")
        for correction in request.corrections:
            row = rows.get(correction.id)
            if row is None:
                raise ValueError(
                    f"correction targets unknown line item id {correction.id!r}"
                )
            for field_name in (
                "raw_item_name",
                "printed_qty",
                "billed_qty",
                "free_qty",
                "billed_rate",
                "tax_percent",
                "mrp",
            ):
                value = getattr(correction, field_name)
                if value is not None:
                    row[field_name] = value

        invoice_number = (request.invoice_number or bundle.get("invoice_number") or "").strip()
        if request.invoice_date:
            try:
                invoice_date = date.fromisoformat(request.invoice_date)
            except ValueError as exc:
                raise ValueError("invoice_date must use YYYY-MM-DD format") from exc
        else:
            invoice_date = _invoice_date(str(bundle.get("invoice_date") or ""))
        if not invoice_number:
            invoice_number = f"INV-{invoice_date.year}-{uuid4().hex[:6].upper()}"
        supplier = bundle.get("suppliers") or None
        supplier_name = (supplier or {}).get("name") or "Supplier"
        supplier_gstin = (supplier or {}).get("gstin") or ""
        skus = await repo.get_canonical_skus(client)
        sku_by_id = {str(sku["id"]): sku for sku in skus}

        invoice_for_history = {
            "id": invoice_id,
            "merchant_id": bundle["merchant_id"],
            "supplier_id": bundle.get("supplier_id"),
            "invoice_date": invoice_date.isoformat(),
        }

        # Fetch the per-SKU supplier and market history concurrently, and only
        # once for duplicate SKUs in one invoice. This reduces the confirm
        # waterfall's PostgREST round trips while preserving its window/gate.
        history_tasks: dict[str, asyncio.Task] = {}
        peer_tasks: dict[str, asyncio.Task] = {}
        for row in rows.values():
            sku_id = row.get("canonical_sku_id")
            if not sku_id:
                continue
            sku_id = str(sku_id)
            if bundle.get("supplier_id") and sku_id not in history_tasks:
                history_tasks[sku_id] = asyncio.create_task(
                    get_supplier_history(invoice_for_history, sku_id)
                )
            if merchant.get("pincode") and sku_id not in peer_tasks:
                peer_tasks[sku_id] = asyncio.create_task(
                    get_pincode_peer_rates(
                        invoice_for_history,
                        sku_id,
                        str(merchant["pincode"]),
                        invoice_date - timedelta(days=14),
                        invoice_date,
                    )
                )
        if history_tasks or peer_tasks:
            await asyncio.gather(*history_tasks.values(), *peer_tasks.values())
        history_by_sku = {sku_id: task.result() for sku_id, task in history_tasks.items()}
        peers_by_sku = {sku_id: task.result() for sku_id, task in peer_tasks.items()}

        response_items: list[AuditedItem] = []
        item_updates: dict[str, dict] = {}
        approved_total = Decimal("0.00")
        overcharge_total = Decimal("0.00")
        issue_summaries: list[str] = []

        for row in rows.values():
            item_id = str(row["id"])
            sku = sku_by_id.get(str(row.get("canonical_sku_id") or ""))
            sku_id = sku["id"] if sku else None
            rate = dec(row["billed_rate"])
            tax_percent = dec(row["tax_percent"])
            supplier_history = history_by_sku.get(str(sku_id), []) if sku_id else []
            peer_rates = peers_by_sku.get(str(sku_id), []) if sku_id else []
            price = analyze_price(
                rate,
                [r["billed_rate"] for r in supplier_history],
                peer_rates,
            )

            line_calc = calculate_line(
                {
                    "raw_item_name": row["raw_item_name"],
                    "billed_qty": row["billed_qty"],
                    "free_qty": row["free_qty"],
                    "billed_rate": row["billed_rate"],
                    "tax_percent": row["tax_percent"],
                    "ocr_confidence": row["ocr_confidence"],
                }
            )
            expected = line_calc.expected_line_total
            # The printed line total is not a stored column; reconstruct it
            # from the original printed qty so a pen edit (printed != billed)
            # still surfaces as overcharge after correction.
            printed_line_total = q2(
                dec(row["printed_qty"]) * rate * (Decimal("1") + tax_percent / Decimal("100"))
            )
            line_delta = q2(printed_line_total - expected)
            math_error = abs(line_delta) >= Decimal("0.01")
            line_overcharge = max(Decimal("0.00"), line_delta)
            approved_total += expected
            overcharge_total += line_overcharge

            has_pen_markup = bool(
                row.get("has_pen_markup")
                or dec(row["printed_qty"]) != dec(row["billed_qty"])
            )
            confidence_review = dec(row["ocr_confidence"]) < Decimal("0.80")
            rate_flagged = price["rate_status"] == "FLAGGED_HIGH"
            market = price["pincode_benchmark"]
            peer_median = market.get("median_rate") if market.get("gate_active") else None
            personal_median = price["supplier_history"].get("median_rate")
            history_display = personal_median if personal_median is not None else rate
            market_display = peer_median if peer_median is not None else history_display
            mandi_band = (
                _peer_band(peer_rates)
                if market.get("gate_active") and peer_rates
                else "Mandi-Pulse inactive (<5 stores)"
            )

            mrp = dec(row["mrp"]) if row.get("mrp") is not None else (
                dec(sku["standard_mrp"]) if sku and sku.get("standard_mrp") is not None else None
            )
            low_margin = bool(
                mrp and mrp > 0
                and ((mrp - line_calc.true_landed_cost) / mrp * Decimal("100")) < Decimal("8")
            )
            findings: list[str] = []
            if rate_flagged:
                findings.append("RATE_HIKE")
            if has_pen_markup:
                findings.append("PEN_EDIT")
            if math_error:
                findings.append("MATH_ERROR")
            if low_margin:
                findings.append("LOW_MARGIN")
            if confidence_review:
                findings.append("LOW_CONFIDENCE_REVIEW")

            if rate_flagged and has_pen_markup:
                discrepancy_type = "RATE_HIKE_AND_PEN_ERROR"
            elif not findings and confidence_review:
                discrepancy_type = "LOW_CONFIDENCE_REVIEW"
            else:
                discrepancy_type = ";".join(findings) if findings else "NONE"

            rate_status = "FLAGGED_HIGH" if (rate_flagged or has_pen_markup or math_error or low_margin) else "OK"
            if findings:
                issue_summaries.append(f"{row['raw_item_name']}: {', '.join(findings)}")

            response_items.append(
                AuditedItem(
                    item_name=row["raw_item_name"],
                    billed_qty=int(row["billed_qty"]),
                    printed_qty=int(row["printed_qty"]),
                    free_qty=int(row["free_qty"]),
                    billed_rate=as_float(q2(rate)),
                    tax_percent=as_float(q2(tax_percent)),
                    true_landed_cost=as_float(line_calc.true_landed_cost),
                    ocr_confidence=float(dec(row["ocr_confidence"])),
                    has_pen_markup=has_pen_markup,
                    discrepancy_type=discrepancy_type,
                    personal_history_rate=as_float(q2(dec(history_display))),
                    mandi_pulse_median=as_float(q2(dec(market_display))),
                    mandi_pulse_band=mandi_band,
                    rate_status=rate_status,
                )
            )

            item_updates[item_id] = {
                "raw_item_name": row["raw_item_name"],
                "printed_qty": int(row["printed_qty"]),
                "billed_qty": int(row["billed_qty"]),
                "free_qty": int(row["free_qty"]),
                "billed_rate": str(q2(rate)),
                "tax_percent": str(q2(tax_percent)),
                "true_landed_cost": str(line_calc.true_landed_cost),
                "mrp": str(q2(mrp)) if mrp is not None else None,
                "has_pen_markup": has_pen_markup,
                "discrepancy_reason": ";".join(findings) if findings else None,
                "mandi_pulse_median": str(q2(dec(peer_median))) if peer_median is not None else None,
            }

        approved_total = q2(approved_total)
        overcharge_total = q2(overcharge_total)
        billed_total = q2(
            dec(request.billed_total)
            if request.billed_total is not None
            else dec(bundle["billed_total"])
        )
        credit = await get_credit_rules().plan(merchant, approved_total, 7)
        audio_url = "/static/audio/demo_alert.wav"  # absent until Sarvam TTS is integrated; UI speaks transcript fallback
        deadline = _ims_deadline(invoice_date)
        flag_reason = "; ".join(issue_summaries) or "Invoice math verified; no flagged line items"
        transcript = (
            f"{supplier_name} bill checked. "
            f"Line-item overcharge of Rs {as_float(overcharge_total):.2f}. "
            f"Recommended payout is Rs {as_float(approved_total):.2f}."
        )
        response = AuditedInvoiceResponse(
            invoice_id=invoice_id,
            supplier_name=supplier_name,
            supplier_gstin=supplier_gstin,
            invoice_number=invoice_number,
            invoice_date=invoice_date.isoformat(),
            billed_total=as_float(billed_total),
            approved_total=as_float(approved_total),
            overcharge_amount=as_float(overcharge_total),
            audio_alert_url=audio_url,
            dispute_crop_url=bundle.get("dispute_crop_url") or "",
            voice_transcript=transcript,
            items=response_items,
            gst_ims_shield=GstImsShield(
                status="SHIELD_READY",
                flag_reason=flag_reason,
                deadline=deadline.isoformat(),
            ),
            split_credit_pre_approval=SplitCreditPreApproval(
                is_eligible=credit.is_eligible,
                max_credit_limit=as_float(credit.max_credit_limit),
                daily_deduction_amount=as_float(credit.daily_deduction),
                tenure_days=7,
                daily_velocity_cap=as_float(credit.daily_cap),
                autopay_mandate_registered=bool(merchant.get("upi_vpa")),
            ),
        )

        await self._persist_confirmation(client, invoice_id, invoice_row={
            "invoice_number": invoice_number,
            "invoice_date": invoice_date.isoformat(),
            "audio_alert_url": audio_url,
            "billed_total": str(billed_total),
            "approved_total": str(approved_total),
            "overcharge_amount": str(overcharge_total),
            "status": repo.INVOICE_STATUS_BILL_VERIFIED,
        }, item_updates=item_updates, supplier_gstin=supplier_gstin or None,
            dispute_proof_url=bundle.get("dispute_crop_url"), deadline=deadline)
        logger.info(
            "draft confirmed invoice_id=%s item_count=%d status=%s",
            invoice_id,
            len(item_updates),
            repo.INVOICE_STATUS_BILL_VERIFIED,
        )
        return response

    async def _persist_draft(
        self,
        client,
        invoice_row: dict,
        line_items: list[dict],
    ) -> None:
        invoice_id = invoice_row["id"]
        try:
            await repo.insert_invoice(client, invoice_row)
            await repo.insert_invoice_line_items(client, line_items)
        except Exception:
            logger.exception("scan draft persistence failed; attempting rollback of invoice_id=%s", invoice_id)
            try:
                await repo.delete_invoice(client, invoice_id)
            except Exception:
                logger.exception("scan draft rollback failed invoice_id=%s", invoice_id)
            crop_url = invoice_row.get("dispute_crop_url") or ""
            if crop_url.startswith("/static/crops/pen_edit_"):
                crop_file = get_settings().static_dir / crop_url.removeprefix("/static/")
                try:
                    crop_file.unlink(missing_ok=True)
                except OSError:
                    logger.warning("could not remove orphaned scan crop")
            raise

    async def _persist_confirmation(
        self,
        client,
        invoice_id: str,
        invoice_row: dict,
        item_updates: dict[str, dict],
        supplier_gstin: Optional[str],
        dispute_proof_url: Optional[str],
        deadline: date,
    ) -> None:
        """Best-effort post-confirm writes (PostgREST has no multi-write
        transaction). Keep the invoice pending until line updates and the
        idempotent IMS insert are complete, then commit bill_verified last."""
        for item_id, payload in item_updates.items():
            await repo.update_invoice_line_item(client, item_id, payload)
        existing_ims = await repo.get_ims_record_for_invoice(client, invoice_id)
        if existing_ims is None:
            await repo.insert_ims_record(
                client,
                {
                    "invoice_id": invoice_id,
                    "gstin_supplier": supplier_gstin,
                    "invoice_number": invoice_row["invoice_number"],
                    "ims_status": "PENDING",
                    "dispute_proof_url": dispute_proof_url,
                    "auto_locked_deadline": deadline.isoformat(),
                },
            )
        await repo.update_invoice(client, invoice_id, invoice_row)


def _normalize(value: str) -> str:
    return "".join(character for character in (value or "").upper() if character.isalnum())


def _match_supplier(supplier_name: str, supplier_gstin: Optional[str], suppliers: list[dict]) -> Optional[dict]:
    if supplier_gstin:
        gstin = _normalize(supplier_gstin)
        match = next((row for row in suppliers if _normalize(row.get("gstin") or "") == gstin), None)
        if match:
            return match
    name = _normalize(supplier_name)
    return next((row for row in suppliers if _normalize(row.get("name") or "") == name), None)


def _match_sku(raw_name: str, skus: list[dict]) -> Optional[dict]:
    target = _normalize(raw_name)
    for sku in skus:
        aliases = sku.get("aliases") or []
        if isinstance(aliases, str):
            aliases = aliases.split("|")
        candidates = [sku.get("product_name") or "", *aliases]
        if any(_normalize(candidate) == target for candidate in candidates):
            return sku
    return None


def _invoice_date(raw_date: Optional[str]) -> date:
    if raw_date:
        try:
            return date.fromisoformat(raw_date)
        except ValueError:
            logger.warning("Gemini returned a non-ISO invoice date; using current date")
    return date.today()


def _ims_deadline(invoice_date: date) -> date:
    if invoice_date.day <= 14:
        return date(invoice_date.year, invoice_date.month, 14)
    if invoice_date.month == 12:
        return date(invoice_date.year + 1, 1, 14)
    return date(invoice_date.year, invoice_date.month + 1, 14)


def _box_array(box) -> Optional[list[int]]:
    if box is None:
        return None
    return [box.ymin, box.xmin, box.ymax, box.xmax]


def _peer_band(peer_rates: list[tuple[str, object]]) -> str:
    prices = [dec(rate) for _, rate in peer_rates]
    if not prices:
        return "Mandi-Pulse inactive (<5 stores)"
    low, high = min(prices), max(prices)
    return f"₹{_format_rupees(low)} - ₹{_format_rupees(high)}"


def _format_rupees(value: Decimal) -> str:
    rounded = value.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return format(rounded, "f")
