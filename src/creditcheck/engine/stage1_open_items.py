"""Stage 1 - Open items & net balance (pipeline step 1).

Read what : AUDIT_HEADER by ACCOUNT_REF - all (non-deleted) transactions +
            OUTSTANDING.
Judge     : lock the current open items (OUTSTANDING != 0) and the net book
            balance (sum of OUTSTANDING across the SALES-ledger rows). This net
            balance must equal what Sage shows as the customer's account balance.
            AUDIT_HEADER holds both ledgers, so on a contra account (same ref on
            the purchase side) the AR net is the S* rows only; the P* side is
            reported separately as purchase_net, not mixed in.
Output    : open-item list + net book balance + purchase_net + full txn list.

Sign convention (Sage): an unpaid sales invoice (SI) carries a positive
OUTSTANDING; a credit (SC) or an unallocated receipt / payment-on-account (SA)
carries a negative OUTSTANDING. Summing OUTSTANDING therefore yields the true
net the customer owes (positive) or that we owe them (negative).
"""

from __future__ import annotations

import datetime
from decimal import ROUND_HALF_UP, Decimal

from ..sage import connection

# Only the columns Stage 1 needs. Full row has 104 columns; keep it lean.
_COLUMNS = [
    "TRAN_NUMBER",
    "TYPE",
    "DATE",
    "ACCOUNT_REF",
    "INV_REF",
    "DETAILS",
    "DUE_DATE",
    "GROSS_AMOUNT",
    "AMOUNT_PAID",
    "OUTSTANDING",
    "PAID_FLAG",
    "HEADER_NUMBER",
]

_ZERO = Decimal("0.00")


def _money(x) -> Decimal:
    """Coerce a Sage float amount to 2-dp Decimal (kills -0.0 / float noise)."""
    d = Decimal(str(x if x is not None else 0)).quantize(_ZERO, rounding=ROUND_HALF_UP)
    # Decimal('-0.00') compares equal to 0 but prints with a sign; normalise it.
    return d + _ZERO if d == _ZERO else d


def open_items(account_ref: str, conn=None) -> dict:
    """Return open items and net book balance for a customer account.

    Reads only; opens its own read-only connection if one is not supplied.
    """
    own_conn = conn is None
    if own_conn:
        conn = connection.connect()
    try:
        ref = connection.quote_literal(account_ref)
        sql = (
            f"SELECT {', '.join(_COLUMNS)} FROM AUDIT_HEADER "
            f"WHERE ACCOUNT_REF = '{ref}' AND DELETED_FLAG = 0"
        )
        rows = connection.query(conn, sql)
    finally:
        if own_conn:
            conn.close()

    for r in rows:
        r["OUTSTANDING"] = _money(r["OUTSTANDING"])
        r["GROSS_AMOUNT"] = _money(r["GROSS_AMOUNT"])
        r["AMOUNT_PAID"] = _money(r["AMOUNT_PAID"])

    rows.sort(key=lambda r: (r["DATE"] or datetime.date.min, r["TRAN_NUMBER"]))

    # AUDIT_HEADER holds BOTH ledgers; a contra account (same ref on the purchase
    # side, i.e. a two-way trade partner) pulls supplier rows too. The AR net that must equal
    # SALES_LEDGER.BALANCE is the SALES side only (TYPE starts 'S'); keep the
    # purchase side separate so the contra is visible, not silently mixed in.
    sales_rows = [r for r in rows if (r["TYPE"] or "")[:1] == "S"]
    purchase_rows = [r for r in rows if (r["TYPE"] or "")[:1] == "P"]

    open_rows = [r for r in sales_rows if r["OUTSTANDING"] != _ZERO]
    net_balance = sum((r["OUTSTANDING"] for r in sales_rows), _ZERO)
    purchase_net = sum((r["OUTSTANDING"] for r in purchase_rows), _ZERO)

    return {
        "account_ref": account_ref,
        "ledger": _detect_ledger(rows),
        "net_balance": net_balance,
        "purchase_net": purchase_net,
        "transaction_count": len(sales_rows),
        "open_item_count": len(open_rows),
        "open_items": open_rows,
        "all_transactions": rows,
    }


def _detect_ledger(rows) -> str:
    """Classify the account as 'sales' (AR), 'purchase' (AP), 'mixed', or
    'unknown' from the transaction TYPE prefixes (S* = sales, P* = purchase).

    This is an AR credit-control tool; AUDIT_HEADER holds both ledgers, so a
    purchase (supplier) account can be pulled by ref. The caller uses this to
    warn when Stage 1 is run against an AP account.
    """
    prefixes = {(r["TYPE"] or "")[:1] for r in rows}
    has_sales = "S" in prefixes
    has_purchase = "P" in prefixes
    if has_sales and has_purchase:
        return "mixed"
    if has_sales:
        return "sales"
    if has_purchase:
        return "purchase"
    return "unknown"
