"""Stage 3 - Split-level reconciliation (pipeline step 3).

Read what : AUDIT_SPLIT grouped by HEADER_NUMBER (NOT TRAN_NUMBER);
            read GROSS_AMOUNT / OUTSTANDING / PAID_FLAG per line.
Judge     : which line of a multi-line contract invoice (VM Batch, one nominal
            per line) the residual sits on. A header whose OUTSTANDING != sum of
            its line OUTSTANDING means a split was missed (usually because
            something grouped by TRAN_NUMBER, which returns only the first line).
Output    : debt pinned to the exact invoice line, plus a self-check identity
            (header OUTSTANDING == sum of line OUTSTANDING) that flags any header
            whose lines don't reconcile.

Why HEADER_NUMBER, not TRAN_NUMBER: a multi-line invoice is ONE header but MANY
splits, each split carrying its OWN TRAN_NUMBER while sharing the header's
HEADER_NUMBER. Grouping by TRAN_NUMBER returns a single line and under-counts;
grouping by HEADER_NUMBER returns the whole invoice. (Confirmed repeatedly in
Stage 2; AUDIT_HEADER.HEADER_NUMBER == AUDIT_SPLIT.HEADER_NUMBER.)

ODBC caveats (see design spec, section 11): no parameter binding / no subqueries;
inline literals and split into separate queries. AUDIT_SPLIT's identity column is
SPLIT_NUMBER; line money lives in GROSS_AMOUNT / OUTSTANDING here (not AUDIT_USAGE).
"""

from __future__ import annotations

import datetime
from decimal import ROUND_HALF_UP, Decimal

from ..sage import connection

# Sales invoices are what carry a residual to pin to a line.
_INVOICE_TYPES = {"SI"}

_ZERO = Decimal("0.00")


def _money(x) -> Decimal:
    """Coerce a Sage float amount to 2-dp Decimal (kills -0.0 / float noise)."""
    d = Decimal(str(x if x is not None else 0)).quantize(_ZERO, rounding=ROUND_HALF_UP)
    return d + _ZERO if d == _ZERO else d


def split_recon(account_ref: str, conn=None) -> dict:
    """Pin each invoice's residual to its individual lines and self-check.

    Returns, per sales invoice, the line-level breakdown (one row per AUDIT_SPLIT
    line) with the residual pinned to the line(s) that carry it, and a list of
    any headers whose line OUTSTANDING does not sum to the header OUTSTANDING.

    Reads only; opens its own read-only connection if one is not supplied.
    """
    own_conn = conn is None
    if own_conn:
        conn = connection.connect()
    try:
        ref = connection.quote_literal(account_ref)

        # --- 1. this account's invoice headers (HEADER_NUMBER -> facts) ------
        headers = connection.query(conn, (
            "SELECT TRAN_NUMBER, HEADER_NUMBER, TYPE, DATE, INV_REF, DETAILS, "
            "GROSS_AMOUNT, OUTSTANDING FROM AUDIT_HEADER "
            f"WHERE ACCOUNT_REF = '{ref}' AND DELETED_FLAG = 0"
        ))
        hdr_by_hnum = {h["HEADER_NUMBER"]: h for h in headers
                       if h["TYPE"] in _INVOICE_TYPES}

        # --- 2. this account's splits, grouped by HEADER_NUMBER -------------
        splits = connection.query(conn, (
            "SELECT SPLIT_NUMBER, TRAN_NUMBER, HEADER_NUMBER, NOMINAL_CODE, "
            "DETAILS, GROSS_AMOUNT, OUTSTANDING, PAID_FLAG FROM AUDIT_SPLIT "
            f"WHERE ACCOUNT_REF = '{ref}' AND DELETED_FLAG = 0"
        ))
        splits_by_hnum: dict = {}
        for s in splits:
            splits_by_hnum.setdefault(s["HEADER_NUMBER"], []).append(s)

        # --- 3. per invoice, break the residual down to its lines -----------
        invoices = []
        mismatches = []
        for hnum, hdr in hdr_by_hnum.items():
            raw_lines = sorted(splits_by_hnum.get(hnum, []),
                               key=lambda s: s["SPLIT_NUMBER"])
            lines = []
            for s in raw_lines:
                out = _money(s["OUTSTANDING"])
                lines.append({
                    "split_number": s["SPLIT_NUMBER"],
                    "tran": s["TRAN_NUMBER"],
                    "nominal": (str(s["NOMINAL_CODE"]).strip()
                                if s["NOMINAL_CODE"] is not None else None),
                    "details": (s["DETAILS"] or "").strip() or None,
                    "gross": _money(s["GROSS_AMOUNT"]),
                    "outstanding": out,
                    "paid_flag": (str(s["PAID_FLAG"]).strip()
                                  if s["PAID_FLAG"] is not None else None),
                    "open": out != _ZERO,
                })

            hdr_out = _money(hdr["OUTSTANDING"])
            line_sum = sum((ln["outstanding"] for ln in lines), _ZERO)
            reconciles = hdr_out == line_sum

            inv = {
                "tran": hdr["TRAN_NUMBER"],
                "header_number": hnum,
                "inv_ref": (hdr["INV_REF"] or "").strip() or None,
                "type": hdr["TYPE"],
                "date": hdr["DATE"],
                "gross": _money(hdr["GROSS_AMOUNT"]),
                "outstanding": hdr_out,
                "line_count": len(lines),
                "line_outstanding_sum": line_sum,
                "reconciles": reconciles,
                "lines": lines,
            }
            invoices.append(inv)
            if not reconciles:
                mismatches.append({
                    "tran": inv["tran"],
                    "inv_ref": inv["inv_ref"],
                    "header_outstanding": hdr_out,
                    "line_sum": line_sum,
                    "difference": _money(hdr_out - line_sum),
                })

        invoices.sort(key=lambda i: (i["date"] or datetime.date.min, i["tran"]))

        return {
            "account_ref": account_ref,
            "invoice_count": len(invoices),
            "multiline_count": sum(1 for i in invoices if i["line_count"] > 1),
            "open_invoice_count": sum(1 for i in invoices if i["outstanding"] != _ZERO),
            "invoices": invoices,
            "mismatches": mismatches,
        }
    finally:
        if own_conn:
            conn.close()
