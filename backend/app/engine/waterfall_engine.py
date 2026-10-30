from collections import defaultdict
from decimal import Decimal
from typing import Any, Iterable

from .math_engine import ZERO, as_decimal, money


def _average(values: Iterable[Decimal]) -> Decimal | None:
    items = list(values)
    if not items:
        return None
    return money(sum(items, ZERO) / Decimal(len(items)))


def _median(values: Iterable[Decimal]) -> Decimal | None:
    items = sorted(values)
    if not items:
        return None
    middle = len(items) // 2
    if len(items) % 2:
        return items[middle]
    return money((items[middle - 1] + items[middle]) / Decimal("2"))


def analyze_price(
    current_rate: Any,
    supplier_history_rates: Iterable[Any],
    peer_rates: Iterable[tuple[str, Any]],
    min_distinct_stores: int = 5,
) -> dict[str, Any]:
    current = money(as_decimal(current_rate, "current_rate"))
    history = [
        money(as_decimal(rate, "supplier_history_rate"))
        for rate in supplier_history_rates
    ][:3]
    supplier_median = _median(history)
    supplier_delta = (
        money(current - supplier_median) if supplier_median is not None else None
    )

    per_store_rates: dict[str, list[Decimal]] = defaultdict(list)
    for merchant_id, rate in peer_rates:
        per_store_rates[str(merchant_id)].append(
            money(as_decimal(rate, "peer_rate"))
        )
    anonymized_rates = [
        _average(rates) for rates in per_store_rates.values()
    ]
    peer_average = _average(rate for rate in anonymized_rates if rate is not None)
    peer_count = len(per_store_rates)
    gate_active = peer_count >= min_distinct_stores
    peer_delta = (
        money(current - peer_average)
        if gate_active and peer_average is not None
        else None
    )

    history_increased = supplier_delta is not None and supplier_delta > ZERO
    peer_increased = peer_delta is not None and peer_delta > ZERO
    return {
        "current_rate": current,
        "supplier_history": {
            "last_3_rates": history,
            "median_rate": supplier_median,
            "delta": supplier_delta,
            "price_increased": history_increased,
        },
        "pincode_benchmark": {
            "peer_store_count": peer_count,
            "average_rate": peer_average if gate_active else None,
            "delta": peer_delta,
            "price_increased": peer_increased,
            "gate_active": gate_active,
        },
        "rate_status": "FLAGGED_HIGH"
        if history_increased or peer_increased
        else "OK",
    }