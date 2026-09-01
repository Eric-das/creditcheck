"""Stage 2 - Allocation chain tracing (pipeline step 2, core).

Read what : AUDIT_USAGE (SPLIT_NUMBER / SPLIT_CROSSREF point at each other)
            -> AUDIT_SPLIT -> AUDIT_HEADER.
Judge     : for every penny, which receipt/credit paid it, on what date, by
            whom. Detect two mis-allocation patterns:
              (a) a credit note split across several unrelated invoices
                  (not a clean 1:1 reversal of its original invoice);
              (b) one cash receipt mis-allocated, forcing a chain of scattered
                  credit re-allocations.
Output    : the full allocation chain per invoice.

Correct chain to resolve "which invoice did this payment pay":
    AUDIT_USAGE.SPLIT_CROSSREF -> AUDIT_SPLIT.TRAN_NUMBER -> AUDIT_HEADER.INV_REF
(Do NOT aggregate AUDIT_SPLIT.INV_REF directly - it mixes same-ref/multi-line
rows across months and yields false conclusions.)

ODBC caveats baked in (see design spec, section 11):
  * AUDIT_USAGE.DATE is an unreliable/garbage value - never SELECT it. Take the
    allocation date from the PAYING transaction's AUDIT_HEADER.DATE instead.
  * AUDIT_SPLIT identity column is SPLIT_NUMBER; it has no AMOUNT column. Amounts
    live in AUDIT_USAGE.AMOUNT.
  * Each allocation is stored twice (once each direction) - query one canonical
    side (invoice on SPLIT_CROSSREF) so each allocation is counted once.
  * un-allocated usage rows are zeroed, not deleted - DELETED_FLAG = 0 keeps the
    live ones and the AMOUNT = 0 rows fall away naturally.
"""

from __future__ import annotations

import datetime
from decimal import ROUND_HALF_UP, Decimal

from ..sage import connection

# Sales-ledger transaction types (AUDIT_HEADER.TYPE).
_INVOICE_TYPES = {"SI"}                 # what a receipt/credit gets allocated TO
_PAYER_TYPES = {"SR", "SA", "SC"}       # receipt / on-account / credit note
_TYPE_NAME = {"SI": "Invoice", "SR": "Receipt", "SA": "On-account",
              "SC": "Credit", "SD": "Discount"}

_ZERO = Decimal("0.00")


def _money(x) -> Decimal:
    """Coerce a Sage float amount to 2-dp Decimal (kills -0.0 / float noise)."""
    d = Decimal(str(x if x is not None else 0)).quantize(_ZERO, rounding=ROUND_HALF_UP)
    return d + _ZERO if d == _ZERO else d


def allocation_chain(account_ref: str, conn=None, progress=None) -> dict:
    """Return, per invoice, the receipts/credits that were allocated to it.

    Reads only; opens its own read-only connection if one is not supplied.

    progress: optional callback(done, total) invoked as invoices are traced, so
    a caller (e.g. the SSE endpoint) can surface a live progress bar. This is the
    slow stage on large accounts, so the count is the honest work signal.
    """
    own_conn = conn is None
    if own_conn:
        conn = connection.connect()
    try:
        ref = connection.quote_literal(account_ref)

        # --- 1. this account's transactions (tran/header_number -> facts) ----
        # A multi-line invoice is ONE header but MANY splits, each split with its
        # OWN TRAN_NUMBER; they all share the header's HEADER_NUMBER. So splits
        # must be grouped by HEADER_NUMBER, never by the header's TRAN_NUMBER
        # (that returns only the first line -> under-counts allocations).
        headers = connection.query(conn, (
            "SELECT TRAN_NUMBER, HEADER_NUMBER, TYPE, DATE, INV_REF, DETAILS, "
            "GROSS_AMOUNT, OUTSTANDING FROM AUDIT_HEADER "
            f"WHERE ACCOUNT_REF = '{ref}' AND DELETED_FLAG = 0"
        ))
        tran_hdr = {h["TRAN_NUMBER"]: h for h in headers}
        hdr_by_hnum = {h["HEADER_NUMBER"]: h for h in headers}

        # --- 2. this account's splits, grouped by HEADER_NUMBER -------------
        splits = connection.query(conn, (
            "SELECT SPLIT_NUMBER, HEADER_NUMBER FROM AUDIT_SPLIT "
            f"WHERE ACCOUNT_REF = '{ref}' AND DELETED_FLAG = 0"
        ))
        split_to_hnum = {s["SPLIT_NUMBER"]: s["HEADER_NUMBER"] for s in splits}
        splits_by_hnum: dict = {}
        for s in splits:
            splits_by_hnum.setdefault(s["HEADER_NUMBER"], []).append(s["SPLIT_NUMBER"])

        # cache: resolve a foreign split (contra / other account) to a header
        _foreign: dict = {}

        def resolve_split(split_number: int) -> dict | None:
            """Map a paying split -> its transaction header facts (any account).

            Goes split -> HEADER_NUMBER -> header, so a multi-line paying
            transaction resolves to its single header (not a stray line-tran).
            """
            hnum = split_to_hnum.get(split_number)
            if hnum is not None and hnum in hdr_by_hnum:
                return hdr_by_hnum[hnum]
            if split_number in _foreign:
                return _foreign[split_number]
            srows = connection.query(conn, (
                "SELECT HEADER_NUMBER FROM AUDIT_SPLIT "
                f"WHERE SPLIT_NUMBER = {int(split_number)}"
            ))
            hdr = None
            if srows:
                hn = srows[0]["HEADER_NUMBER"]
                hrows = connection.query(conn, (
                    "SELECT TRAN_NUMBER, HEADER_NUMBER, TYPE, DATE, INV_REF, "
                    f"ACCOUNT_REF, GROSS_AMOUNT FROM AUDIT_HEADER "
                    f"WHERE HEADER_NUMBER = {int(hn)}"
                ))
                hdr = hrows[0] if hrows else None
            _foreign[split_number] = hdr
            return hdr

        # --- 3. per invoice, gather what was allocated to it ----------------
        invoices = []
        payer_spread: dict = {}     # paying tran -> set of invoice trans it hit

        invoice_trans = [t for t, h in tran_hdr.items() if h["TYPE"] in _INVOICE_TYPES]
        total = len(invoice_trans)
        for idx, tran in enumerate(invoice_trans):
            if progress is not None and (idx % 5 == 0 or idx == total - 1):
                progress(idx + 1, total)
            hdr = tran_hdr[tran]
            # One canonical side only: the invoice line is on SPLIT_CROSSREF, the
            # payer on SPLIT_NUMBER. The mirror row (invoice on SPLIT_NUMBER) has
            # a different CROSSREF and never shows up here, so each allocation is
            # already counted exactly once -- do NOT dedupe by (payer, amount):
            # one credit can legitimately apply the same amount to two lines.
            allocations = []
            for sp in splits_by_hnum.get(hdr["HEADER_NUMBER"], []):
                usage = connection.query(conn, (
                    "SELECT SPLIT_NUMBER, AMOUNT, USER_NAME FROM AUDIT_USAGE "
                    f"WHERE SPLIT_CROSSREF = {int(sp)} AND DELETED_FLAG = 0"
                ))
                for u in usage:
                    amount = _money(u["AMOUNT"])
                    if amount == _ZERO:
                        continue          # zeroed (un-allocated) row
                    payer = resolve_split(u["SPLIT_NUMBER"])
                    payer_tran = payer["TRAN_NUMBER"] if payer else None
                    allocations.append({
                        "by_tran": payer_tran,
                        "by_type": (payer or {}).get("TYPE"),
                        "by_ref": ((payer or {}).get("INV_REF") or "").strip() or None,
                        "by_date": (payer or {}).get("DATE"),
                        "amount": amount,
                        "user": (u.get("USER_NAME") or "").strip() or None,
                    })
                    if payer_tran is not None:
                        payer_spread.setdefault(payer_tran, set()).add(tran)

            allocations.sort(key=lambda a: (a["by_date"] or datetime.date.min,
                                            a["by_tran"] or 0))
            invoices.append({
                "tran": tran,
                "inv_ref": (hdr["INV_REF"] or "").strip() or None,
                "type": hdr["TYPE"],
                "date": hdr["DATE"],
                "gross": _money(hdr["GROSS_AMOUNT"]),
                "outstanding": _money(hdr["OUTSTANDING"]),
                "allocated_total": sum((a["amount"] for a in allocations), _ZERO),
                "allocations": allocations,
            })

        invoices.sort(key=lambda i: (i["date"] or datetime.date.min, i["tran"]))

        # --- 4. mis-allocation flag (a): a credit spread across >1 invoice ---
        credit_spread = []
        for payer_tran, inv_set in payer_spread.items():
            ph = tran_hdr.get(payer_tran)
            if ph and ph["TYPE"] == "SC" and len(inv_set) > 1:
                credit_spread.append({
                    "credit_tran": payer_tran,
                    "credit_ref": (ph["INV_REF"] or "").strip() or None,
                    "spread_over": sorted(inv_set),
                })

        return {
            "account_ref": account_ref,
            "invoice_count": len(invoices),
            "invoices": invoices,
            "credit_spread_flags": credit_spread,
        }
    finally:
        if own_conn:
            conn.close()
