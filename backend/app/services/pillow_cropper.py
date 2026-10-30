"""Visual Dispute Cropper (Module 3).

Isolates handwritten pen strikethrough regions in wide line-item context
using Pillow, applying contextual framing and AI annotation highlights,
and saves the proof crop to /static/crops/.
"""

import io
import logging
from pathlib import Path
from PIL import Image, ImageDraw

from app.contracts import BoundingBox2D
from app.core.config import get_settings

logger = logging.getLogger(__name__)


def crop_pen_markup(
    image_bytes: bytes,
    box: BoundingBox2D,
    invoice_id: str,
) -> str:
    """Crop pen strikethrough region with wide line-item row context and visual annotation.

    Returns the relative URL path to the saved crop image (/static/crops/...).
    """
    settings = get_settings()
    crops_dir = settings.static_dir / "crops"
    crops_dir.mkdir(parents=True, exist_ok=True)

    filename = f"pen_edit_{invoice_id}.jpg"
    file_path = crops_dir / filename

    try:
        image = Image.open(io.BytesIO(image_bytes))
        if image.mode in ("RGBA", "P"):
            image = image.convert("RGB")

        width, height = image.size

        # Convert normalized (0-1000) coordinates to pixel positions
        ymin_px = (box.ymin / 1000.0) * height
        xmin_px = (box.xmin / 1000.0) * width
        ymax_px = (box.ymax / 1000.0) * height
        xmax_px = (box.xmax / 1000.0) * width

        box_w = max(10.0, xmax_px - xmin_px)
        box_h = max(10.0, ymax_px - ymin_px)
        cx = (xmin_px + xmax_px) / 2.0
        cy = (ymin_px + ymax_px) / 2.0

        # Intelligent Row-Level Framing:
        # A dispute proof must show the surrounding item row (name, rates, quantities)
        # rather than a microscopic blur of just the pen stroke.
        crop_w = min(float(width), max(box_w * 4.0, width * 0.75, 550.0))
        crop_h = min(float(height), max(box_h * 4.5, height * 0.18, 220.0))

        x1 = int(max(0, min(cx - crop_w / 2.0, width - crop_w)))
        y1 = int(max(0, min(cy - crop_h / 2.0, height - crop_h)))
        x2 = int(min(width, x1 + crop_w))
        y2 = int(min(height, y1 + crop_h))

        # Crop the high-resolution region
        cropped = image.crop((x1, y1, x2, y2))
        draw = ImageDraw.Draw(cropped)

        # Draw AI highlight bounding box around the exact edit
        rel_x1 = max(4, int(xmin_px - x1 - 6))
        rel_y1 = max(4, int(ymin_px - y1 - 6))
        rel_x2 = min(cropped.width - 4, int(xmax_px - x1 + 6))
        rel_y2 = min(cropped.height - 4, int(ymax_px - y1 + 6))

        # Red highlight box
        draw.rectangle([rel_x1, rel_y1, rel_x2, rel_y2], outline="#ef4444", width=3)

        # "PEN EDIT DETECTED" badge pill
        badge_y = max(2, rel_y1 - 18)
        badge_w = 135
        badge_h = 16
        draw.rectangle(
            [rel_x1, badge_y, min(cropped.width - 4, rel_x1 + badge_w), badge_y + badge_h],
            fill="#ef4444",
        )
        draw.text((rel_x1 + 4, badge_y + 2), "PEN EDIT DETECTED", fill="white")

        # Save crisp JPEG
        cropped.save(file_path, "JPEG", quality=92, optimize=True)

        logger.info(f"[pillow_cropper] Saved high-context annotated pen crop to {file_path}")
        return f"/static/crops/{filename}"

    except Exception as exc:
        logger.error(f"[pillow_cropper] Failed to crop pen markup: {exc}", exc_info=True)
        return "/assets/mock/demo_pen_edit.svg"
