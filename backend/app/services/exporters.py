"""Tally XML / Marg CSV purchase-voucher generators (Module 5 deliverable,
exposed by the Module 2 export endpoint in this slice).

Derivation rule (documented tension, AGENTS.md): amounts come from
invoice_line_items only — the stored invoices.billed_total includes
charges that are not itemized (freight etc.) and must never be used.
All money passes through Decimal, formatted to 2 dp strings.
"""

import html
from datetime import date
from decimal import Decimal

from app.core.money import dec

Q2 = Decimal("0.01")


def _fmt(value) -> str:
    return str(dec(value).quantize(Q2))


def _date_str(value) -> str:
    if isinstance(value, date):
        return value.isoformat()
    return str(value)  # PostgREST DATE arrives as 'YYYY-MM-DD'


def build_tally_xml(invoice: dict, supplier: dict, line_items: list) -> bytes:
    """Minimal Tally Import-Data purchase voucher. GST/ledger detail is
    Module 5's expansion; the shape is a valid Tally XML import envelope."""
    inv_no = invoice.get("invoice_number") or ""
    inv_date = _date_str(invoice.get("invoice_date"))
    party = html.escape((supplier or {}).get("name") or "")
    party_phrase = f'<PARTYNAME>{party}</PARTYNAME><PARTYLEDGERNAME>{party}</PARTYLEDGERNAME>' if party else ""

    entries = []
    total = Decimal("0")
    for item in line_items:
        amount = dec(item["billed_qty"]) * dec(item["billed_rate"])
        total += amount
        entries.append(
            "\n        <ALLINVENTORYENTRIES.LIST>\n"
            f"            <ITEMNAME>{html.escape(item.get('raw_item_name') or '')}</ITEMNAME>\n"
            f"            <BILLEDQTY>{item['billed_qty']} pcs</BILLEDQTY>\n"
            f"            <RATE>{_fmt(item['billed_rate'])}</RATE>\n"
            f"            <AMOUNT>{_fmt(amount)}</AMOUNT>\n"
            f"            <GSTRATE>{_fmt(item.get('tax_percent'))}</GSTRATE>\n"
            "        </ALLINVENTORYENTRIES.LIST>"
        )

    xml = (
        "<ENVELOPE>\n"
        " <HEADER>\n"
        "  <TALLYREQUEST>Import Data</TALLYREQUEST>\n"
        " </HEADER>\n"
        " <BODY>\n"
        "  <IMPORTDATA>\n"
        "   <REQUESTDATA>\n"
        '    <TALLYMESSAGE xmlns:UDF="TallyUDF">\n'
        '     <VOUCHER VCHTYPE="Purchase" ACTION="Create">\n'
        f"      <DATE>{inv_date.replace('-', '')}</DATE>\n"
        f"      <NARRATION>ParchaPay scanned bill {html.escape(inv_no)}</NARRATION>\n"
        f"      <VOUCHERTYPENAME>Purchase</VOUCHERTYPENAME>\n"
        f"      {party_phrase}\n"
        f"      {''.join(entries)}\n"
        f"      <TOTALAMOUNT>{_fmt(total)}</TOTALAMOUNT>\n"
        "     </VOUCHER>\n"
        "    </TALLYMESSAGE>\n"
        "   </REQUESTDATA>\n"
        "  </IMPORTDATA>\n"
        " </BODY>\n"
        "</ENVELOPE>\n"
    )
    return xml.encode("utf-8")


def build_marg_csv(invoice: dict, supplier: dict, line_items: list) -> bytes:
    """Marg CSV purchase voucher: one row per line item (v1 layout agreed
    with the Pillow/Marg export demo; every field from line items)."""
    rows = [
        [
            "Invoice Number",
            "Invoice Date",
            "Supplier Name",
            "Supplier GSTIN",
            "Item Sr No",
            "Item Name",
            "Qty",
            "Free Qty",
            "Rate",
            "GST %",
            "Line Amount",
        ]
    ]
    inv_no = invoice.get("invoice_number") or ""
    inv_date = _date_str(invoice.get("invoice_date"))
    sup_name = (supplier or {}).get("name") or ""
    sup_gstin = (supplier or {}).get("gstin") or ""

    for index, item in enumerate(line_items, start=1):
        amount = dec(item["billed_qty"]) * dec(item["billed_rate"])
        rows.append(
            [
                inv_no,
                inv_date,
                sup_name,
                sup_gstin,
                str(index),
                item.get("raw_item_name") or "",
                str(item["billed_qty"]),
                str(item.get("free_qty", 0)),
                _fmt(item["billed_rate"]),
                _fmt(item.get("tax_percent")),
                _fmt(amount),
            ]
        )

    csv_text = "\n".join(",".join(_csv_field(field) for field in row) for row in rows) + "\n"
    return csv_text.encode("utf-8")


def _csv_field(value: str) -> str:
    """RFC-4180 escaping for the values Marg/Excel choke on."""
    if any(ch in value for ch in ",\"\n"):
        return '"' + value.replace('"', '""') + '"'
    return value
