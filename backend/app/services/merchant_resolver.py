"""Merchant resolution (B1 locked decision, implemented server-side).

Resolution chain (PARCHA_DEMO_MERCHANT_ID / resolution source logged per
request so the mapping is visible in API logs):

  1. Exact `merchants` lookup of the submitted merchant_id (the frontend's
     DEMO_MERCHANT_ID constant stays untouched — zero frontend changes).
  2. `PARCHA_DEMO_MERCHANT_ID` env — MUST be a real seeded merchants.id.
  3. First seeded merchant owning at least one invoice.

Module 2 owns this mapping; Module 4's engine math always ends up on a
real merchant row so the 35% cap and invoice FKs hit actual seeded rows.
"""

import logging
from typing import Optional

logger = logging.getLogger("parchapay.api")


async def resolve_merchant(client, demo_merchant_id: str, submitted_merchant_id: Optional[str]) -> dict:
    """Return a real merchants row for this request (never None)."""
    # 1. Submitted id exists in the seeded data → use it as-is.
    from app.core import repo

    merchant = await repo.get_merchant(client, submitted_merchant_id or "")
    if merchant:
        return merchant

    # 2. Configured demo merchant (a real seeded UUID).
    demo = await repo.get_merchant(client, demo_merchant_id)
    if demo:
        logger.info(
            "merchant resolved via PARCHA_DEMO_MERCHANT_ID (submitted=%r unused/unmapped)",
            submitted_merchant_id,
        )
        return demo

    # 3. First seeded merchant that owns an invoice.
    fallback = await repo.first_merchant_with_invoice(client)
    if fallback is None:
        raise RuntimeError("No seeded merchant found — merchants/invoices tables are empty.")
    logger.info("merchant resolved via first-invoice fallback (no configured demo merchant)")
    return fallback
