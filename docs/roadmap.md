# CreditCheck — Build Roadmap

> Aligned with the design spec (private). Core sequencing rule: **prove the "brain" actually works in code first (cheap, high learning), then spend on packaging it into a product (expensive); dogfood before selling.** The founder is user zero — that's the biggest advantage; don't waste it.

## Phase 0 — Foundation ✅ done
Repo, scaffold, 13-section spec, four UI mockups, vision. All in the private repo.

## Phase 1 — Engine core (stages 1-3) as a CLI tool you use daily
- Fill in `stage1/2/3` against real Sage ODBC; output an Excel/console report (reusing patterns from earlier reconciliation scripts). No UI.
- ✅ **Done when:** for 10-20 real accounts, the engine's verdict == your manual verdict. This is the bedrock gate — *does the brain actually work in code?* If it fails, everything downstream is wasted.
- **Progress (2026-08-18):**
  - Connectivity retired: `connection.connect()` (read-only, getpass fallback so the password need not be stored) + `creditcheck --check`. Confirmed against a live Sage 50 company (v33) — `AUDIT_HEADER` reachable, 104 columns.
  - `stage1_open_items` implemented: `AUDIT_HEADER` by `ACCOUNT_REF`, `DELETED_FLAG = 0`, Decimal money, open items = `OUTSTANDING != 0`, net balance = Σ OUTSTANDING. Ledger detected from TYPE prefix (S/P) with an AP warning.
  - `creditcheck <ACCOUNT_REF>` prints a report. **Validated 1/10-20:** first real account's net balance and open items matched Sage exactly. `cc.bat` launcher added.

## Phase 2 — The "brain": two classifiers + verdict logic
- Turn stage output into dashboard **verdicts** (false overdue / our mis-tag / floating credit / genuine arrears) — i.e. the conservation adjudicator + payment-style classifier, in code.
- ✅ **Done when:** it can scan all accounts and produce the "suspicious list" that matches your judgement. (This is the dashboard's data layer — still headless.)

## Phase 3 — Stages 4-5, evidence intake (the moat, highest value)
- Bank statement import (CSV/PDF parse) → conservation formula; AP screenshot / remittance local OCR; consent-gated Outlook scan; the two self-check nets.
- ✅ **Done when:** for a tangled account, dropping in a bank statement + AP screenshot yields the true net owed, and a deliberately wrong import is caught by the self-check.

## Phase 4 — UI: wrap the engine as a desktop app (Dashboard / Investigation / Proposal)
- ⚠️ **Decision point:** stack choice (Electron / Tauri / WebView2 + Python engine as a subprocess, or a rewrite). Engine and UI have been kept separate throughout, so Phases 1-3 don't depend on this choice.
- ✅ **Done when:** you can do a full day's credit control *inside the app* instead of running scripts.

## Phase 5 — Onboarding / packaging: connect wizard + auto ODBC + installer (make-or-break for external users)
- Implement "auto-detect Sage, auto-create DSN, read-only, encrypted local credential store" + an installer.
- ⚠️ **The #1 risk:** letting someone who isn't you install it and connect to their Sage without touching ODBC settings.
- ✅ **Done when:** a non-technical accountant can install it and connect to their own Sage unaided.

## Phase 6 — Licensing + subscription
- Licence key, online activation/validation, trial period, billing (Stripe etc.).
- ✅ **Done when:** whether the subscription is paid actually gates whether the app runs.

## Phase 7 — Second user / pilot
- Get one real external user (ideally a bookkeeping firm) using it on their own Sage — ideally paying.
- This is what truly validates whether it's a business, and the first real collision with **Sage version fragmentation**.

## Principles throughout
- Keep **engine and UI separate** (the scaffold already does) — the Phase 1-3 engine is reusable whatever the UI choice.
- **De-risk order:** correctness (cheap) → polish (expensive). Don't rush a pretty UI.
- **v1 read-only** is an iron rule throughout.
- **Don't skip ahead:** no multi-company / multi-user / platform thinking before Phase 7 — first get a second person to pay.

## Current next step
**Phase 1 engine trio complete (2026-08-20).** Stage 1 (open items) gate hit 30/30;
Stage 2 (allocation chain) validated ~30 accounts / 779 allocations; Stage 3
(split-level reconciliation) validated 30 accounts / 7,927 SI headers, 0 line
mismatches. See the private build log for detail.

Next: tidy Phase 1 (share the `_money` helper across stages; fold the batch
validator into an in-repo dev tool), then start **Phase 2 — the "brain"**: the
conservation adjudicator + payment-style classifier that turn stage output into
per-account verdicts (false overdue / our mis-tag / floating credit / genuine
arrears) and produce the "suspicious list". Or pick up a backlog item
(by-invoice query; Excel/CSV/PDF export layer).
