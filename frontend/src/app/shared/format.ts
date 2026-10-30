/**
 * Display formatting helpers (Module 1).
 *
 * These are presentation-only. Every subtotal, tax, landed cost, overcharge,
 * and loan number is computed by the backend's Python `decimal.Decimal`
 * engines (CIS Modules 3/4) — the client only renders contract values.
 */

const inr0 = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  maximumFractionDigits: 0,
});

const inr2 = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

/** Whole-rupee display, Indian grouping — e.g. 13860 → "₹13,860" */
export function formatINR(value: number): string {
  return inr0.format(value);
}

/** Rate/landed-cost display — e.g. 140.7 → "₹140.70" */
export function formatINR2(value: number): string {
  return inr2.format(value);
}

/** Percent display without trailing zeros — e.g. 5 → "5%", 0.76 → "76%" */
export function formatPct(value: number, alreadyRatio = false): string {
  const pct = alreadyRatio ? value * 100 : value;
  return `${Number.isInteger(pct) ? pct : pct.toFixed(1)}%`;
}
