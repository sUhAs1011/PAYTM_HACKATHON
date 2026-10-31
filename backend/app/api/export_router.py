"""GET /api/parcha/{id}/export?format=tally|marg — CIS §4 (Module 2 slice 1).

Streams the 1-click purchase voucher for desktop accounting. The
generators (Module 5 deliverable, see app/services/exporters.py) derive
every amount from invoice_line_items — never the stored billed_total.
"""

import logging
import re
from datetime import date

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.core import repo
from app.core.config import EXPORT_FORMATS
from app.core.db import get_client
from app.services.exporters import build_marg_csv, build_tally_xml

logger = logging.getLogger("parchapay.api")
router = APIRouter()

_MEDIA_TYPES = {"tally": "application/xml", "marg": "text/csv"}
_BUILDERS = {"tally": build_tally_xml, "marg": build_marg_csv}


@router.get("/api/parcha/{invoice_id}/export")
async def export_invoice(invoice_id: str, format: str = "tally") -> Response:
    fmt = (format or "").strip().lower()
    if fmt not in EXPORT_FORMATS:
        raise HTTPException(status_code=404, detail=f"unsupported export format {format!r}; use tally or marg")

    client = await get_client()
    bundle = await repo.get_invoice_bundle(client, invoice_id)
    if not bundle:
        raise HTTPException(status_code=404, detail=f"invoice {invoice_id} not found")
    if bundle.get("status") == repo.INVOICE_STATUS_USER_PENDING_REVIEW:
        raise HTTPException(status_code=409, detail="invoice is awaiting merchant review — confirm first")
    supplier = bundle.get("suppliers") or None
    line_items = bundle.get("invoice_line_items") or []
    if not line_items:
        raise HTTPException(status_code=404, detail=f"invoice {invoice_id} has no line items to export")

    payload = _BUILDERS[fmt](bundle, supplier, line_items)
    safe_name = re.sub(r"[^A-Za-z0-9_-]+", "-", bundle.get("invoice_number") or invoice_id)[:60]
    extension = "xml" if fmt == "tally" else "csv"
    filename = f"parchapay-{safe_name}.{extension}"
    logger.info("export invoice=%s format=%s rows=%d", invoice_id, fmt, len(line_items))
    return Response(
        content=payload,
        media_type=_MEDIA_TYPES[fmt],
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
