"""Money helpers — Decimal is law for every rupee value (locked rule).

PostgREST returns numeric columns as JSON numbers (Python floats). The
shortest-repr round-trip keeps 2-dp values intact, but every conversion
still goes through Decimal, and every stored/derived amount is quantized
to 2 dp with ROUND_HALF_UP before it is written or serialized.
"""

from decimal import ROUND_HALF_UP, Decimal

Q2 = Decimal("0.01")


def q2(value: Decimal) -> Decimal:
    """Quantize to 2 dp, half-up."""
    return value.quantize(Q2, rounding=ROUND_HALF_UP)


def dec(value) -> Decimal:
    """Convert a wire/DB value to Decimal via str (float-safe)."""
    return Decimal(str(value))


def as_float(value: Decimal) -> float:
    """Serialize a quantized Decimal into the contract's JSON number type."""
    return float(str(q2(value)))
