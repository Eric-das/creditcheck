"""FastAPI app: connect once, then serve the three engine stages per account.

Design (matches the product's data choice = live direct-read, not a local
cache):
  * POST /api/connect  opens ONE read-only Sage connection with the credentials
    typed on the connect screen and holds it in memory for the session. As the
    "first scan" it also reads the customer list (ref / name / balance) so the
    query screen can offer/validate account refs instantly.
  * GET  /api/accounts returns that customer list (from the connect-time scan).
  * GET  /api/account/{ref}?stages=1,2,3 runs the engine LIVE against Sage and
    returns Stage 1/2/3 as JSON. Always current, never cached.

pyodbc connections are not thread-safe, and FastAPI runs sync endpoints in a
thread pool, so every use of the shared connection is guarded by a lock.
"""
from __future__ import annotations

import json
import os
import queue
import threading

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .. import config
from ..sage import connection
from ..engine import (
    stage1_open_items,
    stage2_allocation_chain,
    stage3_split_recon,
)
from .serialize import to_jsonable

app = FastAPI(title="CreditCheck", version="0.1")


class _State:
    """Session state: the live read-only connection + the connect-time scan."""

    def __init__(self) -> None:
        self.conn = None
        self.lock = threading.Lock()
        self.dsn: str | None = None
        self.username: str | None = None
        self.accounts: list[dict] = []


state = _State()


def _load_accounts(conn) -> list[dict]:
    """The 'first scan': customer ref / name / balance from SALES_LEDGER.

    Counted and sorted in Python (the Sage ODBC driver is weak on aggregates);
    this is a light read that powers the query screen's list and autocomplete.
    """
    rows = connection.query(conn, (
        "SELECT ACCOUNT_REF, NAME, BALANCE FROM SALES_LEDGER "
        "WHERE RECORD_DELETED = 0"
    ))
    out = []
    for r in rows:
        ref = (r["ACCOUNT_REF"] or "").strip()
        if not ref:
            continue
        out.append({
            "ref": ref,
            "name": (r["NAME"] or "").strip(),
            "balance": round(float(r["BALANCE"] or 0), 2),
        })
    out.sort(key=lambda a: a["ref"])
    return out


class ConnectBody(BaseModel):
    password: str
    username: str | None = None
    dsn: str | None = None


@app.get("/api/health")
def health():
    return {"ok": True, "connected": state.conn is not None,
            "dsn": state.dsn, "account_count": len(state.accounts)}


@app.post("/api/connect")
def connect(body: ConnectBody):
    """Open the read-only connection and run the first scan (customer list)."""
    cfg = config.load()
    dsn = (body.dsn or cfg["sage"].get("dsn") or "").strip()
    username = (body.username or cfg["sage"].get("username") or "").strip()
    if not dsn:
        raise HTTPException(status_code=400, detail="No Sage DSN configured.")

    try:
        conn = connection.open_connection(dsn, username, body.password)
    except Exception as e:  # pyodbc.Error and friends
        raise HTTPException(status_code=502,
                            detail=f"Could not connect to Sage: {e}")

    try:
        accounts = _load_accounts(conn)
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=502,
                            detail=f"Connected, but the first scan failed: {e}")

    with state.lock:
        if state.conn is not None:
            try:
                state.conn.close()
            except Exception:
                pass
        state.conn = conn
        state.dsn = dsn
        state.username = username
        state.accounts = accounts

    return {"ok": True, "dsn": dsn, "username": username,
            "account_count": len(accounts)}


@app.get("/api/accounts")
def accounts():
    if state.conn is None:
        raise HTTPException(status_code=409,
                            detail="Not connected. POST /api/connect first.")
    return {"account_count": len(state.accounts), "accounts": state.accounts}


@app.get("/api/account/{ref}")
def account(ref: str, stages: str = "1,2,3"):
    """Run the requested stages LIVE for one account and return JSON."""
    if state.conn is None:
        raise HTTPException(status_code=409,
                            detail="Not connected. POST /api/connect first.")

    want = {s.strip() for s in stages.split(",") if s.strip()}
    result: dict = {"account_ref": ref}
    with state.lock:
        conn = state.conn
        try:
            if "1" in want:
                result["stage1"] = stage1_open_items.open_items(ref, conn=conn)
            if "2" in want:
                result["stage2"] = stage2_allocation_chain.allocation_chain(
                    ref, conn=conn)
            if "3" in want:
                result["stage3"] = stage3_split_recon.split_recon(ref, conn=conn)
        except Exception as e:
            raise HTTPException(status_code=500,
                                detail=f"Query failed for {ref}: {e}")

    return JSONResponse(to_jsonable(result))


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@app.get("/api/account/{ref}/stage2/stream")
def stage2_stream(ref: str):
    """Stream Stage 2 with live progress (SSE) - it is the slow stage.

    The trace runs in a worker thread; a queue carries progress + the final
    result back to a sync generator that Starlette iterates in its thread pool.
    """
    if state.conn is None:
        raise HTTPException(status_code=409,
                            detail="Not connected. POST /api/connect first.")

    def gen():
        q: "queue.Queue" = queue.Queue()

        def cb(done, total):
            q.put(("progress", {"done": done, "total": total}))

        def run():
            # Hold the lock for the whole trace: one shared read-only pyodbc
            # connection, used by a single thread at a time.
            with state.lock:
                try:
                    r = stage2_allocation_chain.allocation_chain(
                        ref, conn=state.conn, progress=cb)
                    q.put(("result", to_jsonable(r)))
                except Exception as e:
                    q.put(("error", {"detail": f"Query failed for {ref}: {e}"}))

        threading.Thread(target=run, daemon=True).start()
        while True:
            kind, payload = q.get()
            yield _sse(kind, payload)
            if kind in ("result", "error"):
                break

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/api/invoice/{inv_ref}")
def find_by_invoice(inv_ref: str):
    """Find which customer account(s) an invoice number belongs to.

    INV_REF is not globally unique, so this can return several accounts - the UI
    lists them all for the user to pick.
    """
    if state.conn is None:
        raise HTTPException(status_code=409,
                            detail="Not connected. POST /api/connect first.")
    safe = connection.quote_literal(inv_ref.strip())
    with state.lock:
        rows = connection.query(state.conn, (
            "SELECT ACCOUNT_REF FROM AUDIT_HEADER "
            f"WHERE INV_REF = '{safe}' AND DELETED_FLAG = 0"
        ))
    by_ref = {a["ref"]: a for a in state.accounts}
    matches, seen = [], set()
    for r in rows:
        ar = (r["ACCOUNT_REF"] or "").strip()
        if not ar or ar in seen:
            continue
        seen.add(ar)
        a = by_ref.get(ar, {"ref": ar, "name": "", "balance": 0})
        matches.append({"ref": a["ref"], "name": a.get("name", ""),
                        "balance": a.get("balance", 0), "via_invoice": inv_ref})
    return {"invoice": inv_ref, "matches": matches}


# Serve the front end (built in Phase 4b) if it is present, so opening "/" shows
# the app. Guarded so the API still starts before the web assets exist.
_WEB_DIR = os.path.join(os.path.dirname(__file__), "web")
if os.path.isdir(_WEB_DIR):
    app.mount("/", StaticFiles(directory=_WEB_DIR, html=True), name="web")
