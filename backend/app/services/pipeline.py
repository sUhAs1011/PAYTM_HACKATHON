"""ParchaPipeline — the Module 2 ⇄ Module 3/4 seam (scan path).

Module 2 orchestrates; the *actual* work (Gemini 2.5 Flash extraction,
Pillow crop, embeddings — Module 3; deterministic audit — Module 4) lives
behind this seam. When those modules land, their implementation object is
registered with `set_pipeline` and NOTHING in the gateway/routers changes.

Provisional `FixturePipeline`: returns the CIS §5 golden fixture shaped as
a full AuditedInvoiceResponse. Purpose (plan §3, task 5):
  - /scan is demonstrable end-to-end over the real REST surface before
    Module 3/4 exist (frontend recovers gracefully either way);
  - it performs ZERO database writes, so the seeded FK/invariant dataset
    (AGENTS.md) is never touched by demo traffic.
"""

import json
import logging
from typing import Optional, Protocol

from app.contracts import AuditedInvoiceResponse
from app.core.config import fixture_candidates

logger = logging.getLogger("parchapay.api")


class ParchaPipeline(Protocol):
    """Interface Module 3/4 implement: (raw bill) → audited invoice payload."""

    async def extract_and_audit(
        self, image_bytes: bytes, content_type: str, merchant: dict
    ) -> AuditedInvoiceResponse:  # pragma: no cover - interface
        ...


_pipeline: Optional[ParchaPipeline] = None


def set_pipeline(implementation: ParchaPipeline) -> None:
    """Integration point for Module 3/4: register their real pipeline."""
    global _pipeline
    _pipeline = implementation
    logger.info("ParchaPipeline seam replaced: %s", type(implementation).__name__)


def get_pipeline() -> ParchaPipeline:
    if _pipeline is None:
        raise RuntimeError("Pipeline not initialised — app startup failed to load the fixture.")
    return _pipeline


class FixturePipeline:
    """Provisional scan backend: validates the golden fixture once, returns
    its audited payload for every scan. Contract URLs are returned verbatim
    (the frontend demo-mode renders the bundled SVG stand-in; once live
    /static exists the same URLs are served by the API)."""

    def __init__(self) -> None:
        self._response: Optional[AuditedInvoiceResponse] = None

    def load(self) -> AuditedInvoiceResponse:
        if self._response is None:
            last_error = None
            for path in fixture_candidates():
                try:
                    raw = json.loads(path.read_text(encoding="utf-8-sig"))
                    self._response = AuditedInvoiceResponse.model_validate(raw)
                    logger.info("golden fixture loaded from %s", path)
                    return self._response
                except Exception as exc:  # try next candidate
                    last_error = exc
            raise RuntimeError(f"golden fixture not loadable from {fixture_candidates()}: {last_error}")
        return self._response

    async def extract_and_audit(
        self, image_bytes: bytes, content_type: str, merchant: dict
    ) -> AuditedInvoiceResponse:
        # Fixture mode ignores the bytes on purpose (no Gemini yet). The
        # merchant row is accepted so the eventual real pipeline's signature
        # is exercised today.
        return self.load()
