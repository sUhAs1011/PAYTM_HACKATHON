from decimal import Decimal
from typing import Any

from pydantic import BaseModel


class ItemPriceAnalysis(BaseModel):
    line_item_id: str
    item_name: str
    canonical_sku_id: str | None
    analysis: dict[str, Any]


class InvoicePriceAnalysisResponse(BaseModel):
    invoice_id: str
    pincode: str
    items: list[ItemPriceAnalysis]
