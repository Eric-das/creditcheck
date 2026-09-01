"""Command-line entry point.

  creditcheck --check          connectivity self-test (read a sample row, exit)
  creditcheck <ACCOUNT_REF>    Stage 1 report: net book balance + open items
  creditcheck <ACCOUNT_REF> --chain
                               also run Stage 2: allocation chain per invoice
  creditcheck <ACCOUNT_REF> --recon
                               also run Stage 3: split-level reconciliation
"""

from __future__ import annotations

import argparse
import sys


def _fmt_money(d) -> str:
    return f"£{d:,.2f}"


def _run_stage1(account_ref: str, conn=None) -> int:
    """Run Stage 1 for one account and print a report to compare with Sage."""
    from .engine import stage1_open_items

    try:
        result = stage1_open_items.open_items(account_ref, conn=conn)
    except FileNotFoundError as e:
        print(f"[X] {e}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"[X] Stage 1 failed for {account_ref}: {e}", file=sys.stderr)
        return 1

    print(f"Account {result['account_ref']}")
    if result["ledger"] == "purchase":
        print("[!] This looks like a PURCHASE (supplier / AP) account. CreditCheck "
              "is an AR tool - the 'customer owes' framing does not apply here.")
    elif result["ledger"] == "mixed":
        print("[!] This account has both sales and purchase transactions "
              "(possible contra / same-ref customer & supplier).")
        print(f"    Purchase-side net (AP, shown separately): "
              f"{_fmt_money(result['purchase_net'])}")
    print(f"Net book balance : {_fmt_money(result['net_balance'])}")
    print(
        f"Transactions     : {result['transaction_count']} non-deleted"
        f"   |   Open items: {result['open_item_count']}"
    )

    if not result["open_items"]:
        print("\nNo open items - account is square.")
        return 0

    print("\nOpen items (OUTSTANDING != 0):")
    print(f"  {'TRAN':>7}  {'TYPE':<4}  {'DATE':<10}  {'INV_REF':<16}  "
          f"{'OUTSTANDING':>13}  {'DUE':<10}")
    for r in result["open_items"]:
        date = r["DATE"].isoformat() if r["DATE"] else ""
        due = r["DUE_DATE"].isoformat() if r["DUE_DATE"] else ""
        inv = (r["INV_REF"] or "")[:16]
        print(f"  {r['TRAN_NUMBER']:>7}  {r['TYPE']:<4}  {date:<10}  {inv:<16}  "
              f"{_fmt_money(r['OUTSTANDING']):>13}  {due:<10}")
    return 0


def _run_stage2(account_ref: str, conn=None) -> int:
    """Run Stage 2 (allocation chain) for one account and print it."""
    from .engine import stage2_allocation_chain

    try:
        result = stage2_allocation_chain.allocation_chain(account_ref, conn=conn)
    except FileNotFoundError as e:
        print(f"[X] {e}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"[X] Stage 2 failed for {account_ref}: {e}", file=sys.stderr)
        return 1

    print(f"\nAllocation chain - {result['account_ref']}"
          f"   ({result['invoice_count']} invoice(s))")
    for inv in result["invoices"]:
        date = inv["date"].isoformat() if inv["date"] else ""
        state = "OPEN" if inv["outstanding"] else "cleared"
        print(f"\n  {inv['type']} {inv['inv_ref'] or ''}  {date}  "
              f"gross {_fmt_money(inv['gross'])}  "
              f"[{state} {_fmt_money(inv['outstanding'])}]")
        if not inv["allocations"]:
            print("      (no receipts/credits allocated)")
        for a in inv["allocations"]:
            adate = a["by_date"].isoformat() if a["by_date"] else ""
            who = f" by {a['user']}" if a["user"] else ""
            print(f"      <- {_fmt_money(a['amount']):>11}  "
                  f"{(a['by_type'] or '?'):<3} {a['by_ref'] or '':<16} {adate}{who}")

    flags = result["credit_spread_flags"]
    if flags:
        print("\n[!] Credit notes split across several invoices (review):")
        for f in flags:
            print(f"      SC {f['credit_ref'] or f['credit_tran']} "
                  f"spread over trans {f['spread_over']}")
    return 0


def _run_stage3(account_ref: str, conn=None) -> int:
    """Run Stage 3 (split-level reconciliation) for one account and print it."""
    from .engine import stage3_split_recon

    try:
        result = stage3_split_recon.split_recon(account_ref, conn=conn)
    except FileNotFoundError as e:
        print(f"[X] {e}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"[X] Stage 3 failed for {account_ref}: {e}", file=sys.stderr)
        return 1

    print(f"\nSplit reconciliation - {result['account_ref']}"
          f"   ({result['invoice_count']} invoice(s), "
          f"{result['multiline_count']} multi-line, "
          f"{result['open_invoice_count']} open)")

    # Self-check first: this is the forensic signal (a header whose lines don't
    # sum to it means a split was missed).
    mismatches = result["mismatches"]
    if mismatches:
        print(f"\n[!] {len(mismatches)} header(s) fail the line self-check "
              "(header OUTSTANDING != sum of line OUTSTANDING):")
        for m in mismatches:
            print(f"      tran {m['tran']} {m['inv_ref'] or '':<16} "
                  f"header {_fmt_money(m['header_outstanding'])} vs "
                  f"lines {_fmt_money(m['line_sum'])} "
                  f"(diff {_fmt_money(m['difference'])})")
    else:
        print("    Self-check OK: every header's lines sum to its OUTSTANDING.")

    open_invoices = [i for i in result["invoices"] if i["outstanding"] != 0]
    if not open_invoices:
        print("\nNo open invoices - nothing to pin.")
        return 0

    print("\nResidual pinned to line (open invoices):")
    for inv in open_invoices:
        date = inv["date"].isoformat() if inv["date"] else ""
        tag = f" [{inv['line_count']} lines]" if inv["line_count"] > 1 else ""
        print(f"\n  {inv['type']} {inv['inv_ref'] or ''}  {date}  "
              f"gross {_fmt_money(inv['gross'])}  "
              f"open {_fmt_money(inv['outstanding'])}{tag}")
        for ln in inv["lines"]:
            marker = "->" if ln["open"] else "  "
            nominal = (ln["nominal"] or "")
            details = (ln["details"] or "")[:34]
            print(f"    {marker} n/c {nominal:<6} {details:<34} "
                  f"gross {_fmt_money(ln['gross']):>11}  "
                  f"open {_fmt_money(ln['outstanding']):>11}")
    return 0


def _run_check() -> int:
    """Connect to Sage read-only and report what came back."""
    from .sage import connection

    try:
        conn = connection.connect()
    except FileNotFoundError as e:
        print(f"[X] {e}", file=sys.stderr)
        return 2
    except Exception as e:  # pyodbc.Error and friends
        print(f"[X] Could not connect to Sage: {e}", file=sys.stderr)
        return 1

    print("[OK] Connected to Sage (read-only).")
    try:
        info = connection.probe(conn, "AUDIT_HEADER")
    except Exception as e:
        print(f"[X] Connected, but reading AUDIT_HEADER failed: {e}", file=sys.stderr)
        return 1
    finally:
        conn.close()

    cols = info["columns"]
    print(f"[OK] AUDIT_HEADER reachable - {len(cols)} columns.")
    print("     Columns:", ", ".join(cols))
    if info["sample"] is None:
        print("     (table is empty)")
    else:
        print("     Sample row:")
        for k, v in info["sample"].items():
            print(f"       {k} = {v!r}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="creditcheck",
        description="Forensic reconciliation for AR credit control (read-only).",
    )
    parser.add_argument("account", nargs="?", help="Sage customer account ref")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Test the Sage connection (read a sample row) and exit.",
    )
    parser.add_argument(
        "--chain",
        action="store_true",
        help="Also run Stage 2: the allocation chain per invoice.",
    )
    parser.add_argument(
        "--recon",
        action="store_true",
        help="Also run Stage 3: split-level reconciliation (residual per line).",
    )
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    if args.check:
        return _run_check()

    if args.account:
        # Open ONE read-only connection and share it across stages, so --chain
        # does not prompt for the password a second time.
        from .sage import connection
        try:
            conn = connection.connect()
        except FileNotFoundError as e:
            print(f"[X] {e}", file=sys.stderr)
            return 2
        except Exception as e:  # pyodbc.Error and friends
            print(f"[X] Could not connect to Sage: {e}", file=sys.stderr)
            return 1
        try:
            rc = _run_stage1(args.account, conn)
            if rc == 0 and args.chain:
                rc = _run_stage2(args.account, conn)
            if rc == 0 and args.recon:
                rc = _run_stage3(args.account, conn)
        finally:
            conn.close()
        return rc

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
