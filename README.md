# CreditCheck (working title)

Local-first **forensic reconciliation engine** for accounts-receivable credit control.

## What it does

Given a customer account, work out **whether they really owe money at the due date, and on exactly which line** — with an evidence trail — *before* any chasing happens.

Unlike chase-only tools (Chaser, Satago), CreditCheck first gets the ledger *correct*: it traces allocation chains, reconciles at split level, and separates **real debt** from **our own mis-tagging**.

> Sage is a *system of record*, not a *system of investigation*. It faithfully shows whatever was entered — including mistakes. CreditCheck lives in that blind spot.

## MVP scope (v0 — this repo)

The pure-Sage, fully-automatable core (no external data needed):

- **Stage 1 — Open items:** pull all transactions for an account, find open items + net balance.
- **Stage 2 — Allocation chain:** trace, per invoice, which receipt/credit paid it, when, and by whom (`AUDIT_USAGE`).
- **Stage 3 — Split reconciliation:** which *line* of a multi-line invoice the residual sits on (group by `HEADER_NUMBER`).

Later stages (④ conservation vs bank / customer AP, ⑤ email archaeology) require external evidence and are **out of MVP scope**.

## Architecture

Local desktop app that connects to the user's **own local Sage 50** via ODBC. **Data never leaves the machine.** Read-only in v1 — the tool produces *proposals*; a human executes any allocation inside Sage.

## Setup

1. Python 3.12+
2. `pip install -e .`
3. Copy `config.example.json` → `config.json` and set your Sage ODBC DSN. (`config.json` is git-ignored — never commit credentials or customer data.)
4. `creditcheck <ACCOUNT_REF>`

## Status

Engine stages 1–3 are implemented and validated against a live Sage 50 v33
company (30 accounts, ~779 allocations, ~7,900 invoice headers, zero line
mismatches). A local desktop UI (FastAPI + pywebview) wraps the engine —
`run_app.py` or the PyInstaller one-file build. Stages 4–5 (external evidence)
are design-stage only; see `docs/roadmap.md` and the mockups in `docs/mockups/`.

This started as a personal side project to scratch a real credit-control itch;
it is shared as-is in the hope the ODBC/allocation-tracing patterns are useful.
All sample data in docs and mockups is fictional.

## License

MIT — see [LICENSE](LICENSE).
