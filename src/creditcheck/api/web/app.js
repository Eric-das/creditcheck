"use strict";

// ---- state -----------------------------------------------------------------
let ACCOUNTS = [];          // [{ref,name,balance}] from the first scan
let INV_MATCHES = [];       // accounts found via an invoice-number search
let CURRENT = null;         // selected account ref
let ACTIVE_TAB = 1;
let STREAM = null;          // active Stage 2 EventSource
const CACHE = {};           // CACHE[ref] = {1:stage1, 2:stage2, 3:stage3}

// ---- helpers ---------------------------------------------------------------
const $ = (id) => document.getElementById(id);

function fmt(x) {
  const n = Number(x || 0);
  const s = Math.abs(n).toLocaleString("en-GB", {minimumFractionDigits: 2, maximumFractionDigits: 2});
  return (n < 0 ? "-£" : "£") + s;
}
function dmy(iso) {
  if (!iso) return "";
  const p = String(iso).slice(0, 10).split("-");
  return p.length === 3 ? `${p[2]}/${p[1]}/${p[0]}` : iso;
}
function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"]/g, c =>
    ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
}
function amtCell(x) {
  const n = Number(x || 0);
  return `<td class="amt ${n < 0 ? "neg" : "pos"}">${fmt(n)}</td>`;
}
function tokenize(q) {
  return q ? q.split(/[\s,;]+/).filter(Boolean) : [];
}

// ---- connect ---------------------------------------------------------------
async function connect() {
  const btn = $("c-btn"), err = $("c-err");
  err.classList.add("hidden");
  btn.disabled = true; btn.textContent = "Connecting…";
  try {
    const r = await fetch("/api/connect", {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        dsn: $("c-dsn").value.trim(),
        username: $("c-user").value.trim(),
        password: $("c-pass").value,
      }),
    });
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || "Connection failed");
    $("connect").classList.add("hidden");
    $("mainapp").classList.remove("hidden");
    $("t-company").textContent = data.dsn;
    $("t-scan").textContent = `First scan: ${data.account_count} customer accounts`;
    await loadAccounts();
  } catch (e) {
    err.textContent = e.message;
    err.classList.remove("hidden");
  } finally {
    btn.disabled = false; btn.textContent = "Connect & run first scan →";
  }
}

async function loadAccounts() {
  const r = await fetch("/api/accounts");
  const data = await r.json();
  ACCOUNTS = data.accounts || [];
  renderList();
}

// ---- upper: query + client list -------------------------------------------
function rowHtml(a, viaInv) {
  const tag = viaInv
    ? ` <span class="pill p-amb"><span class="d"></span>inv ${esc(viaInv)}</span>` : "";
  return `<tr class="row ${a.ref === CURRENT ? "sel" : ""}" data-ref="${esc(a.ref)}">
    <td class="acc">${esc(a.ref)}${tag}</td>
    <td>${esc(a.name)}</td>${amtCell(a.balance)}</tr>`;
}

function renderList() {
  const q = $("q-input").value.trim().toLowerCase();
  const tokens = tokenize(q);
  let rows;
  if (tokens.length === 0) {
    rows = ACCOUNTS.filter(a => Number(a.balance) !== 0)
                   .sort((a, b) => Math.abs(b.balance) - Math.abs(a.balance));
    $("q-hint").textContent =
      `${rows.length} accounts with an open balance (of ${ACCOUNTS.length} total). Type a code/name to search; press Enter to also search by invoice number.`;
  } else {
    rows = ACCOUNTS.filter(a => {
      const hay = (a.ref + " " + a.name).toLowerCase();
      return tokens.some(t => hay.includes(t));
    });
    $("q-hint").textContent = `${rows.length} match${INV_MATCHES.length ? ` · ${INV_MATCHES.length} via invoice` : ""}. Press Enter to search unmatched terms as invoice numbers.`;
  }

  const tb = $("acctrows");
  const invRows = INV_MATCHES.map(m => rowHtml(m, m.via_invoice));
  const localRows = rows.slice(0, 400).map(a => rowHtml(a));
  if (invRows.length === 0 && localRows.length === 0) {
    tb.innerHTML = `<tr><td colspan="3" class="empty">No matching accounts. Press Enter to try the term as an invoice number.</td></tr>`;
    return;
  }
  tb.innerHTML = invRows.join("") + localRows.join("");
  tb.querySelectorAll("tr.row").forEach(tr =>
    tr.addEventListener("click", () => selectAccount(tr.dataset.ref)));
}

// Enter: treat unmatched terms as invoice numbers and look up their accounts.
async function searchByInvoice() {
  const tokens = tokenize($("q-input").value.trim());
  if (tokens.length === 0) return;
  const matched = new Set();
  ACCOUNTS.forEach(a => {
    const hay = (a.ref + " " + a.name).toLowerCase();
    tokens.forEach(t => { if (hay.includes(t.toLowerCase())) matched.add(t); });
  });
  const invTokens = tokens.filter(t => !matched.has(t));
  if (invTokens.length === 0) { renderList(); return; }
  $("q-hint").textContent = "Searching by invoice number…";
  const found = [], seen = new Set();
  for (const t of invTokens) {
    try {
      const r = await fetch(`/api/invoice/${encodeURIComponent(t)}`);
      const d = await r.json();
      (d.matches || []).forEach(m => {
        const key = m.ref + "|" + m.via_invoice;
        if (!seen.has(key)) { seen.add(key); found.push(m); }
      });
    } catch (e) { /* ignore a bad token */ }
  }
  INV_MATCHES = found;
  renderList();
}

// ---- select + tabs ---------------------------------------------------------
function selectAccount(ref) {
  CURRENT = ref;
  const a = ACCOUNTS.find(x => x.ref === ref) || INV_MATCHES.find(x => x.ref === ref);
  $("l-head").innerHTML = `${esc(ref)} <small>${esc(a ? a.name : "")}</small>`;
  document.querySelectorAll("#acctrows tr.row").forEach(tr =>
    tr.classList.toggle("sel", tr.dataset.ref === ref));
  setActiveTab(1);
  loadTab(1);
}

function setActiveTab(n) {
  ACTIVE_TAB = n;
  [1, 2, 3].forEach(i => {
    $("tabbtn" + i).classList.toggle("active", i === n);
    $("tab" + i).classList.toggle("active", i === n);
  });
}

async function loadTab(n) {
  if (!CURRENT) return;
  const el = $("tab" + n);
  const cached = CACHE[CURRENT] && CACHE[CURRENT][n];
  if (cached) { render(n, el, cached); return; }
  if (n === 2) { loadStage2Stream(el, CURRENT); return; }
  el.innerHTML = `<div class="loading">Querying Sage live for ${esc(CURRENT)} — Stage ${n}…</div>`;
  try {
    const r = await fetch(`/api/account/${encodeURIComponent(CURRENT)}?stages=${n}`);
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || "Query failed");
    (CACHE[CURRENT] = CACHE[CURRENT] || {})[n] = data;
    render(n, el, data);
  } catch (e) {
    el.innerHTML = `<div class="selfcheck bad">${esc(e.message)}</div>`;
  }
}

// Stage 2 over SSE, with a live progress bar (it is the slow stage).
function loadStage2Stream(el, ref) {
  if (STREAM) { STREAM.close(); STREAM = null; }
  el.innerHTML = progressHtml(0, 0);
  let done = false;
  const es = new EventSource(`/api/account/${encodeURIComponent(ref)}/stage2/stream`);
  STREAM = es;
  es.addEventListener("progress", (e) => {
    const d = JSON.parse(e.data);
    updateProgress(el, d.done, d.total);
  });
  es.addEventListener("result", (e) => {
    done = true; es.close(); if (STREAM === es) STREAM = null;
    const data = {stage2: JSON.parse(e.data)};
    (CACHE[ref] = CACHE[ref] || {})[2] = data;
    if (CURRENT === ref && ACTIVE_TAB === 2) renderStage2(el, data.stage2);
  });
  es.addEventListener("error", (e) => {
    if (done) return;                    // normal close after result
    let msg = "Live stream interrupted. Try the tab again.";
    try { if (e.data) msg = JSON.parse(e.data).detail; } catch (_) {}
    es.close(); if (STREAM === es) STREAM = null;
    el.innerHTML = `<div class="selfcheck bad">${esc(msg)}</div>`;
  });
}

function progressHtml(done, total) {
  const pct = total ? Math.round(done / total * 100) : 0;
  return `<div class="prog">
    <div class="prog-label">Tracing allocation chain live from Sage…
      <span id="prog-count">${total ? done + "/" + total : "starting…"}</span></div>
    <div class="prog-track"><div class="prog-bar" id="prog-bar" style="width:${pct}%"></div></div>
    <div class="searchhint">Stage 2 walks every invoice on this account, so large accounts take a moment.</div>
  </div>`;
}
function updateProgress(el, done, total) {
  const bar = el.querySelector("#prog-bar"), cnt = el.querySelector("#prog-count");
  if (bar) bar.style.width = (total ? Math.round(done / total * 100) : 0) + "%";
  if (cnt) cnt.textContent = `${done}/${total}`;
}

function render(n, el, data) {
  if (n === 1) renderStage1(el, data.stage1);
  else if (n === 2) renderStage2(el, data.stage2);
  else renderStage3(el, data.stage3);
}

// ---- Stage 1 ---------------------------------------------------------------
function renderStage1(el, s) {
  if (!s) { el.innerHTML = `<div class="empty">No data.</div>`; return; }
  const ledgerNote = s.ledger === "purchase"
    ? `<div class="selfcheck bad">This looks like a PURCHASE (supplier) account — the "customer owes" framing does not apply.</div>`
    : s.ledger === "mixed"
    ? `<div class="selfcheck bad">Mixed ledger (possible contra). Purchase-side net shown separately: ${fmt(s.purchase_net)}.</div>`
    : "";
  const cards = `<div class="cards">
    <div class="card ${Number(s.net_balance) < 0 ? "ok" : "warn"}"><div class="k">Net book balance</div><div class="v">${fmt(s.net_balance)}</div><div class="n">${Number(s.net_balance) < 0 ? "we owe them / in credit" : "customer owes"}</div></div>
    <div class="card"><div class="k">Open items</div><div class="v">${s.open_item_count}</div><div class="n">OUTSTANDING ≠ 0</div></div>
    <div class="card"><div class="k">Transactions</div><div class="v">${s.transaction_count}</div><div class="n">non-deleted, sales side</div></div>
  </div>`;
  let table;
  if (!s.open_items || s.open_items.length === 0) {
    table = `<div class="selfcheck ok">No open items — account is square.</div>`;
  } else {
    const body = s.open_items.map(r =>
      `<tr><td class="acc">${r.TRAN_NUMBER}</td><td>${esc(r.TYPE)}</td>
        <td>${dmy(r.DATE)}</td><td class="acc">${esc(r.INV_REF || "")}</td>
        ${amtCell(r.OUTSTANDING)}<td>${dmy(r.DUE_DATE)}</td></tr>`).join("");
    table = `<div class="panel"><h3>Open items (OUTSTANDING ≠ 0)</h3>
      <table><thead><tr><th>Tran</th><th>Type</th><th>Date</th><th>Inv ref</th><th class="amt">Outstanding</th><th>Due</th></tr></thead>
      <tbody>${body}</tbody></table></div>`;
  }
  el.innerHTML = ledgerNote + cards + table;
}

// ---- Stage 2 (with secondary invoice search) -------------------------------
function stage2BlockHtml(inv) {
  const state = Number(inv.outstanding) !== 0
    ? `<span class="pill p-amb"><span class="d"></span>open ${fmt(inv.outstanding)}</span>`
    : `<span class="pill p-grn"><span class="d"></span>cleared</span>`;
  const rows = (inv.allocations || []).map(a =>
    `<tr><td class="arrow">←</td>${amtCell(a.amount)}<td>${esc(a.by_type || "?")}</td>
      <td class="acc">${esc(a.by_ref || "")}</td><td>${dmy(a.by_date)}</td>
      <td class="muted">${esc(a.user || "")}</td></tr>`).join("")
    || `<tr><td colspan="6" class="muted">(no receipts/credits allocated)</td></tr>`;
  return `<div class="invblock">
    <div class="h"><span><b>${esc(inv.type)} ${esc(inv.inv_ref || "")}</b> · ${dmy(inv.date)} · gross ${fmt(inv.gross)}</span>${state}</div>
    <table><tbody>${rows}</tbody></table></div>`;
}

function renderStage2Blocks(container, invoices, emptyMsg) {
  container.innerHTML = invoices.length
    ? invoices.map(stage2BlockHtml).join("")
    : `<div class="empty">${emptyMsg || "No invoices."}</div>`;
}

function renderStage2(el, s) {
  if (!s) { el.innerHTML = `<div class="empty">No data.</div>`; return; }
  let flags = "";
  if (s.credit_spread_flags && s.credit_spread_flags.length) {
    flags = `<div class="selfcheck bad">⚠ ${s.credit_spread_flags.length} credit note(s) split across several invoices (review):<br>` +
      s.credit_spread_flags.map(f =>
        `SC ${esc(f.credit_ref || f.credit_tran)} → trans ${f.spread_over.join(", ")}`).join("<br>") + `</div>`;
  }
  const shown = s.invoices.filter(i => (i.allocations && i.allocations.length) || Number(i.outstanding) !== 0);
  const hidden = s.invoices.length - shown.length;
  const note = `<div class="searchhint" style="margin-bottom:12px">${s.invoice_count} invoice(s); showing ${shown.length}${hidden ? `, ${hidden} zero-value hidden` : ""}. Use the box to jump to a specific invoice.</div>`;
  el.innerHTML = flags + note +
    `<div class="invsearch"><input id="s2q" class="inp" placeholder="Filter by invoice number — single or several (space / comma separated). Searches all invoices."></div>
     <div id="s2blocks"></div>`;
  const container = el.querySelector("#s2blocks");
  renderStage2Blocks(container, shown);
  const inp = el.querySelector("#s2q");
  inp.addEventListener("input", () => {
    const toks = tokenize(inp.value.trim().toLowerCase());
    if (toks.length === 0) { renderStage2Blocks(container, shown); return; }
    const filtered = s.invoices.filter(i =>
      toks.some(t => String(i.inv_ref || "").toLowerCase().includes(t)));
    renderStage2Blocks(container, filtered, "No invoices match that number.");
  });
}

// ---- Stage 3 (with secondary invoice search) -------------------------------
function stage3BlockHtml(inv) {
  const tag = inv.line_count > 1 ? ` · ${inv.line_count} lines` : "";
  const open = Number(inv.outstanding) !== 0;
  const state = open
    ? `<span class="pill p-amb"><span class="d"></span>open ${fmt(inv.outstanding)}</span>`
    : `<span class="pill p-grn"><span class="d"></span>cleared</span>`;
  const rows = inv.lines.map(ln =>
    `<tr><td class="arrow">${ln.open ? "→" : ""}</td>
      <td class="acc">${esc(ln.nominal || "")}</td><td>${esc(ln.details || "")}</td>
      ${amtCell(ln.gross)}${amtCell(ln.outstanding)}</tr>`).join("");
  return `<div class="invblock">
    <div class="h"><span><b>${esc(inv.type)} ${esc(inv.inv_ref || "")}</b> · ${dmy(inv.date)} · gross ${fmt(inv.gross)}${tag}</span>${state}</div>
    <table><thead><tr><th></th><th>n/c</th><th>Details</th><th class="amt">Gross</th><th class="amt">Open</th></tr></thead>
    <tbody>${rows}</tbody></table></div>`;
}

function renderStage3Blocks(container, invoices, emptyMsg) {
  container.innerHTML = invoices.length
    ? invoices.map(stage3BlockHtml).join("")
    : `<div class="empty">${emptyMsg || "No matching invoices."}</div>`;
}

function renderStage3(el, s) {
  if (!s) { el.innerHTML = `<div class="empty">No data.</div>`; return; }
  let banner;
  if (s.mismatches && s.mismatches.length) {
    banner = `<div class="selfcheck bad">⚠ ${s.mismatches.length} header(s) fail the self-check (header OUTSTANDING ≠ sum of line OUTSTANDING):<br>` +
      s.mismatches.map(m => `tran ${m.tran} ${esc(m.inv_ref || "")}: header ${fmt(m.header_outstanding)} vs lines ${fmt(m.line_sum)} (diff ${fmt(m.difference)})`).join("<br>") + `</div>`;
  } else {
    banner = `<div class="selfcheck ok">✓ Self-check OK — every header's lines sum to its OUTSTANDING.</div>`;
  }
  const summary = `<div class="searchhint" style="margin-bottom:12px">${s.invoice_count} SI · ${s.multiline_count} multi-line · ${s.open_invoice_count} open.</div>`;
  const open = s.invoices.filter(i => Number(i.outstanding) !== 0);
  el.innerHTML = banner + summary +
    `<div class="invsearch"><input id="s3q" class="inp" placeholder="Filter by invoice number — single or several (space / comma separated). Searches all invoices; empty shows open only."></div>
     <div id="s3blocks"></div>`;
  const container = el.querySelector("#s3blocks");
  renderStage3Blocks(container, open, "No open invoices — nothing to pin.");
  const inp = el.querySelector("#s3q");
  inp.addEventListener("input", () => {
    const toks = tokenize(inp.value.trim().toLowerCase());
    if (toks.length === 0) {
      renderStage3Blocks(container, open, "No open invoices — nothing to pin.");
      return;
    }
    const filtered = s.invoices.filter(i =>
      toks.some(t => String(i.inv_ref || "").toLowerCase().includes(t)));
    renderStage3Blocks(container, filtered, "No invoices match that number.");
  });
}

// ---- wire up ---------------------------------------------------------------
$("c-btn").addEventListener("click", connect);
$("c-pass").addEventListener("keydown", e => { if (e.key === "Enter") connect(); });
$("q-input").addEventListener("input", () => { INV_MATCHES = []; renderList(); });
$("q-input").addEventListener("keydown", e => {
  if (e.key === "Enter") { e.preventDefault(); searchByInvoice(); }
});
[1, 2, 3].forEach(n =>
  $("tabbtn" + n).addEventListener("click", () => { setActiveTab(n); loadTab(n); }));
