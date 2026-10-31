import argparse
import math
import re
from pathlib import Path

from google import genai
from google.genai import types

from app.contracts import BoundingBox2D, RawExtractedInvoice
from app.core.config import get_settings
from app.services.gemini_vision import SYSTEM_INSTRUCTION

MODEL_NAME = "gemini-2.5-flash"
USER_PROMPT = (
    "Extract all invoice details, line items, and pen markup bounding boxes "
    "adhering strictly to the schema."
)
IMAGE_DIR = Path(__file__).resolve().parent / "tests" / "test_images"
IMAGE_CASES = (
    {
        "name": "marked_bill",
        "path": IMAGE_DIR / "736b7d7e-64d8-491d-9ea8-59ec3d08ca5b.png",
        "target_item": "PENS",
        "ground_truth": BoundingBox2D(
            ymin=529,
            xmin=58,
            ymax=591,
            xmax=133,
        ),
        "ground_truth_note": "approximate manual box around the PENS strike-through and rewrite",
    },
    {
        "name": "clean_control",
        "path": IMAGE_DIR / "IMG20261031112933.jpg",
        "target_item": None,
        "ground_truth": None,
        "ground_truth_note": "no visible pen edit; control for false positives",
    },
)
PROMPT_VARIANTS = (
    (
        "current_baseline",
        "",
    ),
    (
        "union_box",
        """For a visible pen correction, draw one tight axis-aligned box that encloses the complete ink edit: both the crossed-out original and its handwritten replacement. Do not box only one of the two values.""",
    ),
    (
        "full_image_coordinates",
        """Return the pen_markup_box in the coordinate system of the entire uploaded image, not a row crop or detail region. The origin is the image's top-left corner, x increases to the right, y increases downward, and each coordinate is normalized to 0-1000.""",
    ),
    (
        "row_and_ink_contrast",
        """First identify the line-item row containing the physical strike-through. Then box only the inked strike-through and replacement in that row. Do not substitute a separate value in the QTY, TOTAL, or RATE column, and do not box headers, item names, or nearby rows.""",
    ),
)


def _normalize_name(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", value.upper())


def _find_target(
    invoice: RawExtractedInvoice, target_item: str
):
    target = _normalize_name(target_item)
    return next(
        (
            item
            for item in invoice.line_items
            if target in _normalize_name(item.raw_item_name)
        ),
        None,
    )


def _box_iou(actual: BoundingBox2D, expected: BoundingBox2D) -> float:
    actual_x1, actual_y1 = actual.xmin, actual.ymin
    actual_x2, actual_y2 = actual.xmax, actual.ymax
    expected_x1, expected_y1 = expected.xmin, expected.ymin
    expected_x2, expected_y2 = expected.xmax, expected.ymax

    intersection_width = max(
        0, min(actual_x2, expected_x2) - max(actual_x1, expected_x1)
    )
    intersection_height = max(
        0, min(actual_y2, expected_y2) - max(actual_y1, expected_y1)
    )
    intersection = intersection_width * intersection_height
    actual_area = max(0, actual_x2 - actual_x1) * max(0, actual_y2 - actual_y1)
    expected_area = max(0, expected_x2 - expected_x1) * max(
        0, expected_y2 - expected_y1
    )
    union = actual_area + expected_area - intersection
    return intersection / union if union else 0.0


def _center_error(actual: BoundingBox2D, expected: BoundingBox2D) -> float:
    actual_x = (actual.xmin + actual.xmax) / 2
    actual_y = (actual.ymin + actual.ymax) / 2
    expected_x = (expected.xmin + expected.xmax) / 2
    expected_y = (expected.ymin + expected.ymax) / 2
    return math.hypot(actual_x - expected_x, actual_y - expected_y)


def _call_model(
    client,
    image_bytes: bytes,
    mime_type: str,
    prompt_suffix: str,
) -> RawExtractedInvoice:
    system_instruction = SYSTEM_INSTRUCTION
    if prompt_suffix:
        system_instruction = f"{SYSTEM_INSTRUCTION}\n\nPROMPT VARIANT:\n{prompt_suffix}"

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=[
            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
            USER_PROMPT,
        ],
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            response_mime_type="application/json",
            response_schema=RawExtractedInvoice,
            temperature=0.1,
        ),
    )
    if response.parsed and isinstance(response.parsed, RawExtractedInvoice):
        return response.parsed
    if response.text:
        return RawExtractedInvoice.model_validate_json(response.text)
    raise ValueError("Gemini returned no structured invoice response")


def _evaluate_case(
    invoice: RawExtractedInvoice,
    case: dict,
) -> dict:
    if case["target_item"]:
        item = _find_target(invoice, case["target_item"])
        box = item.pen_markup_box if item else None
        expected = case["ground_truth"]
        return {
            "target_found": item is not None,
            "has_pen_markup": item.has_pen_markup if item else False,
            "quantity": (
                f"{item.printed_qty}->{item.billed_qty}" if item else "missing"
            ),
            "box": box.model_dump() if box else None,
            "iou": _box_iou(box, expected) if box and expected else 0.0,
            "center_error": _center_error(box, expected)
            if box and expected
            else None,
            "false_positive_count": None,
        }

    false_positives = [
        item
        for item in invoice.line_items
        if item.has_pen_markup or item.pen_markup_box is not None
    ]
    return {
        "target_found": None,
        "has_pen_markup": None,
        "quantity": None,
        "box": None,
        "iou": None,
        "center_error": None,
        "false_positive_count": len(false_positives),
    }


def _format_box(box: dict | None) -> str:
    if box is None:
        return "none"
    return "[{ymin},{xmin},{ymax},{xmax}]".format(**box)


def _error_code(exc: Exception) -> str:
    response = getattr(exc, "response", None)
    for value in (
        getattr(exc, "code", None),
        getattr(exc, "status_code", None),
        getattr(response, "status_code", None),
    ):
        if value is not None:
            return str(value)
    return "unknown"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--image",
        action="append",
        choices=[case["name"] for case in IMAGE_CASES],
        help="Image case to include; repeat for multiple cases. Defaults to all.",
    )
    parser.add_argument(
        "--prompt",
        action="append",
        choices=[name for name, _ in PROMPT_VARIANTS],
        help="Prompt style to include; repeat for multiple styles. Defaults to all.",
    )
    args = parser.parse_args(argv)
    selected_cases = [
        case for case in IMAGE_CASES if not args.image or case["name"] in args.image
    ]
    selected_prompts = [
        prompt
        for prompt in PROMPT_VARIANTS
        if not args.prompt or prompt[0] in args.prompt
    ]

    settings = get_settings()
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured")

    client = genai.Client(api_key=settings.gemini_api_key)
    results = []
    for case in selected_cases:
        image_bytes = case["path"].read_bytes()
        mime_type = "image/png" if case["path"].suffix.lower() == ".png" else "image/jpeg"
        for prompt_name, prompt_suffix in selected_prompts:
            try:
                invoice = _call_model(client, image_bytes, mime_type, prompt_suffix)
                metrics = _evaluate_case(invoice, case)
                results.append(
                    {
                        "image": case["name"],
                        "prompt": prompt_name,
                        "metrics": metrics,
                        "error_type": None,
                        "error_code": None,
                    }
                )
            except Exception as exc:
                results.append(
                    {
                        "image": case["name"],
                        "prompt": prompt_name,
                        "metrics": None,
                        "error_type": type(exc).__name__,
                        "error_code": _error_code(exc),
                    }
                )

    print("# Gemini pen-box prompt benchmark")
    print()
    print(
        "Model: `{}`; temperature: `0.1`; calls attempted: {}; "
        "images: {}; production prompt file unchanged.".format(
            MODEL_NAME,
            len(selected_cases) * len(selected_prompts),
            ", ".join(case["name"] for case in selected_cases),
        )
    )
    print()
    print(
        "The marked-image ground truth is an approximate manual box; "
        "confirm it visually before treating the IoU as definitive."
    )
    for case in selected_cases:
        gt = case["ground_truth"]
        if gt:
            print(
                "Marked-image target box: `{}`; {}".format(
                    _format_box(gt.model_dump()), case["ground_truth_note"]
                )
            )
    print()
    print(
        "| Image | Prompt style | Status | PENS qty | Markup flag | Box | IoU | "
        "Center error (norm.) | Clean false positives | Error |"
    )
    print("| --- | --- | --- | --- | ---: | --- | ---: | ---: | ---: | --- |")

    for result in results:
        metrics = result["metrics"]
        if metrics is None:
            error = "{} ({})".format(
                result["error_type"], result["error_code"]
            )
            print(
                "| {} | {} | ERROR | — | — | — | — | — | — | {} |".format(
                    result["image"], result["prompt"], error
                )
            )
            continue
        is_marked = result["image"] == "marked_bill"
        center_error = (
            "{:.1f}".format(metrics["center_error"])
            if metrics["center_error"] is not None
            else "—"
        )
        print(
            "| {} | {} | OK | {} | {} | {} | {} | {} | {} | — |".format(
                result["image"],
                result["prompt"],
                metrics["quantity"] or "—",
                metrics["has_pen_markup"] if is_marked else "—",
                _format_box(metrics["box"]),
                "{:.3f}".format(metrics["iou"])
                if metrics["iou"] is not None
                else "—",
                center_error,
                metrics["false_positive_count"]
                if not is_marked
                else "—",
            )
        )

    selected_image_names = {case["name"] for case in selected_cases}
    summary: dict[str, dict] = {}
    if "marked_bill" in selected_image_names:
        for prompt_name, _ in selected_prompts:
            marked = next(
                result
                for result in results
                if result["prompt"] == prompt_name
                and result["image"] == "marked_bill"
            )
            clean = next(
                (
                    result
                    for result in results
                    if result["prompt"] == prompt_name
                    and result["image"] == "clean_control"
                ),
                None,
            )
            if marked["metrics"] is None or (clean and clean["metrics"] is None):
                continue
            marked_metrics = marked["metrics"]
            clean_metrics = clean["metrics"] if clean else None
            summary[prompt_name] = {
                "iou": marked_metrics["iou"],
                "detected": bool(
                    marked_metrics["target_found"]
                    and marked_metrics["has_pen_markup"]
                    and marked_metrics["box"]
                ),
                "false_positives": clean_metrics["false_positive_count"]
                if clean_metrics
                else None,
                "center_error": marked_metrics["center_error"],
            }

    eligible = [
        (name, result)
        for name, result in summary.items()
        if result["detected"]
        and (
            "clean_control" not in selected_image_names
            or result["false_positives"] == 0
        )
    ]
    if eligible:
        winner, _ = max(
            eligible,
            key=lambda item: (
                item[1]["iou"],
                -(
                    item[1]["center_error"]
                    if item[1]["center_error"] is not None
                    else float("inf")
                ),
            ),
        )
        print()
        print(
            "Preliminary best: `{}` (detected the marked row and ranked highest "
            "by IoU/center error).".format(winner)
        )
        if "clean_control" in selected_image_names:
            print("The selected prompt also had no false positives on the clean control.")
        else:
            print("Clean-control false positives were not evaluated in this run.")
    else:
        print()
        if "clean_control" in selected_image_names:
            print(
                "No prompt met both criteria (marked-row detection and zero "
                "clean-control false positives); do not declare a winner from this run."
            )
        else:
            print("No prompt localized the marked row; do not declare a winner from this run.")
    print("This is a one-run-per-prompt comparison, not a statistical evaluation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
