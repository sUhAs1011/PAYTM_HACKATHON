"""Gemini 3.6 Flash Vision Client (Module 3).

Extracts structured invoice line items, tax details, free/scheme units,
handwritten pen adjustments, and 2D bounding boxes normalized to 0-1000.
Uses the stable Gemini 3.6 Flash model with structured output.
"""

import logging
from google import genai
from google.genai import types

from app.contracts import BoundingBox2D, ExtractedLineItem, RawExtractedInvoice
from app.core.config import get_settings

logger = logging.getLogger(__name__)

SYSTEM_INSTRUCTION = """You are ParchaPay AI's multimodal vision engine specialized in Indian wholesale invoices (parchas), challans, handwritten delivery chits, and cash memos.
Extract all line items, rates, quantities, and supplier details VERBATIM from the user-uploaded bill image.

CRITICAL INSTRUCTIONS:
1. SUPPLIER & TOTALS:
   - Extract the supplier/distributor business name at the top (e.g. 'SHARMAJI WHOLESALE DISTRIBUTORS').
   - Extract GSTIN if written (e.g. '29AABCU9603R1ZM').
   - Extract Date and Bill/Invoice number if written (e.g. 'INV-402', '31-10-2026').
   - Extract `printed_grand_total`: the final grand total written or printed on the bill (e.g. 1637.00).

2. LINE ITEMS:
   - Extract each item row verbatim (e.g., 'FORTUNE OIL 1L', 'PENS', 'PARLEG').
   - `unit_rate`: the rate per unit written for that item (e.g. 134.00, 10.00, 20.00). If rate is in parentheses like '(134.00)' or '(10.00)', extract the positive number (134.0, 10.0).
   - `line_total`: the total written for that line on the paper (e.g. 1407, 110, 120).
   - `gst_percent`: if tax percentage is not explicitly stated on the chit, set it to 0.0.

3. HANDWRITTEN PEN EDITS & STRIKETHROUGHS (CRITICAL):
   - In Indian wholesale delivery, items are frequently adjusted at the delivery point.
   - A pen edit occurs when someone uses a pen to physically STRIKE THROUGH / CROSS OUT an original quantity or item, and writes the replacement quantity.
   - Read the original printed quantity and the handwritten replacement exactly as visible; do not infer a standard correction or rewrite a digit based on a demo example.
   - `has_pen_markup` = True only for a visible strike-through/cross-out and replacement; `printed_qty` is the original and `billed_qty` is the accepted replacement.
   - `pen_markup_box` = tight 2D bounding box [ymin, xmin, ymax, xmax] normalized to 0-1000 around the actual pen edit.
   - STRICT RULE FOR CLEAN / UNEDITED LINES:
     * If there is NO strikethrough or crossing-out on an item (such as 'FORTUNE OIL 1L' or 'PARLEG'):
       `has_pen_markup` MUST be False.
       `pen_markup_box` MUST be null.
       `printed_qty` MUST equal `billed_qty`.
     * Parentheses, standard handwriting, or darkening a letter (e.g. the 'E' in 'FORTUNE') is NOT a pen markup! Only actual cross-outs / strikethroughs count as pen markup.

4. CONFIDENCE SCORE:
   - Rate `confidence_score` between 0.00 and 1.00 based on handwriting clarity.
"""


def extract_invoice_from_image(
    image_bytes: bytes,
    mime_type: str = "image/jpeg",
) -> RawExtractedInvoice:
    """Send bill image to Gemini 3.6 Flash with strict Pydantic response_schema.

    Raises RuntimeError if GEMINI_API_KEY is not configured or if inference fails.
    """
    settings = get_settings()

    if not settings.gemini_api_key:
        error_msg = (
            "GEMINI_API_KEY is not set! Please add GEMINI_API_KEY=your_key to your .env file "
            "and restart Docker Compose."
        )
        logger.error(f"[gemini_vision] {error_msg}")
        raise RuntimeError(error_msg)

    clean_key = settings.gemini_api_key.strip().strip("'\"")
    client = genai.Client(api_key=clean_key)
    image_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)

    model_name = "gemini-3.6-flash"
    logger.info(f"[gemini_vision] Executing VLM extraction using model: {model_name}...")

    try:
        response = client.models.generate_content(
            model=model_name,
            contents=[
                image_part,
                "Extract all invoice details, line items, and pen markup bounding boxes adhering strictly to the schema.",
            ],
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                response_mime_type="application/json",
                response_schema=RawExtractedInvoice,
                temperature=0.1,
            ),
        )

        if response.parsed and isinstance(response.parsed, RawExtractedInvoice):
            logger.info("[gemini_vision] extraction completed model=%s line_count=%d", model_name, len(response.parsed.line_items))
            return response.parsed

        if response.text:
            logger.info("[gemini_vision] validating structured response model=%s", model_name)
            return RawExtractedInvoice.model_validate_json(response.text)

        raise ValueError(f"Empty response received from {model_name}")

    except Exception as exc:
        logger.error("[gemini_vision] Gemini extraction failed error_type=%s", type(exc).__name__)
        raise RuntimeError(f"Gemini 3.6 Flash extraction failed ({type(exc).__name__})") from exc
