# CreditCheck — Vision & End State

> Strategic north star for the product. Read this when day-to-day detail makes you lose sight of where it's going.

## One-line end state

> A **"Sage credit-control investigation desk"** that runs on the credit controller's own PC — packaging a scarce expert's judgement (working out whether a customer really owes money, and on which line) into software, sold on subscription.

In essence: **one expert's brain, productised.** The product doesn't invent a need — it copies what a rare, slow, expensive specialist does every day, and gives it to SMEs who can't hire that specialist.

## Product form

- An **installed Windows desktop application** — Start-menu icon, its own window, opened like Sage 50 or desktop Outlook. **Not a website / browser tab.**
- It *has* to be desktop: the product connects to the user's **local Sage 50 via ODBC** and processes everything **on the machine**, so the data never leaves. A browser is sandboxed and can't reach local Sage files.
- The "dashboard" is simply the **home screen inside** that app — the layout, not the delivery mechanism.
- Likely built with web UI wrapped in a native shell (Electron / Tauri / WebView2): looks like the mockups, ships as a real `.exe` with local access.

## What it feels like to use

Open the app in the morning (connected to your own Sage):

- **Dashboard mode** — overnight it scanned every customer. The home screen is a **"suspicious list"**: which book balances are false (receipts not allocated), which allocation chains are broken, which credits are floating. Green = ignore. Red = click in.
- **Investigation desk** — open a red account and the Sage-side story line is already laid out (which payment paid which invoice, on which line, with tran numbers). It says *"just confirm the actual cash"* — drop in the bank statement / customer AP screenshot / remittance, it reconciles locally and tells you the **true net owed** and **what's real debt vs our own mis-tag**, and pulls the related PO / dispute emails from Outlook alongside.
- **Proposal** — it hands you the steps (which allocations, which email) as a **proposal**. A human reviews and posts. **The tool never writes to Sage.**

Throughout: **data never leaves the PC** — the decisive edge over cloud-only chase tools (Chaser, Satago).

## Business form

- **Delivery:** downloadable desktop app + a cloud service that only checks the subscription licence (never touches the data).
- **Who pays:** first, internal credit controllers / accountants like the founder (SME, one person per set of books); then, up a tier, **bookkeeping firms** (one-to-many clients, stronger willingness to pay — likely the real money).
- **Pricing:** per-seat / per-company-set monthly subscription. The core value (cross-source reconciliation, ④⑤) is "only-we-can-do-it", so it can carry a real price — not a £9.99 Excel add-in.

## Where the moat deepens

- Table-stakes / speed value: **stages ②③** (surfacing the allocation chain, split-level residuals). A skilled Sage user could do these by hand, slowly — so this is a "saves time / removes the need for an expert" value. Replaceable in principle.
- Un-substitutable value: **stages ④⑤** (conservation vs bank/AP, email archaeology). The data isn't in Sage, so no Sage expert can do it inside Sage. **This is the only true moat — push the product's weight here.**

## Honest strategic forks (the end state won't be a straight line)

1. **Software may drift into software + service.** Early customers can't install ODBC themselves — you'll hand-hold a few. You may find selling *"we'll clean your tangled ledger"* as a service earns faster than the software alone. End state may be a hybrid: software-led, white-glove service alongside.
2. **Platform bet.** We're betting on **Sage 50** (the founder's turf). But Sage 50 is a **shrinking desktop platform**; new customers drift to cloud Xero/QBO. Scaling eventually forces the question: build a cloud version on Xero's API — which is almost a different product. **Sage = deep moat, shrinking pool.** This is the biggest strategic trade-off.
3. **Single-operator tool vs team system.** If bookkeeping firms become the main buyer, the product gets pulled toward multi-company, multi-user, collaboration, audit trails — from a sharp investigation desk into a full credit-control management suite. More valuable, but heavier and harder.
4. **IP.** Whether this can really be sold still hinges on the employer-IP question deferred at the start. It doesn't change the product's form, but it decides whose end state this is.

## The end state I'd back

Not the next big SaaS platform. Rather: **a narrow-and-deep, high-margin subscription product that owns the "Sage 50 credit control" niche and serves hundreds-to-thousands of SMEs / bookkeeping firms — controllable by one person or a small team.** Narrow — but nobody in that niche understands it better than the founder.

---

*Interface previews for the four screens (Connect → Dashboard → Investigation → Proposal) live in [`mockups/`](mockups/).*
