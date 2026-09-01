"""Thin wrapper around the Sage 50 ODBC data source.

Hard-won caveats baked in (see design spec, "ODBC hard tips"):
  * The Sage ODBC driver does NOT support parameter binding or date parameters.
    Inline literal values into the WHERE clause; filter dates in Python.
  * It does NOT support subqueries (a SELECT inside WHERE raises "Invalid filter").
    Split into two queries.
  * Read-only. This engine never writes back to Sage.

Credentials policy (privacy-first):
  * config.json may hold the Sage username; the password is best left blank so it
    is *never stored on disk*. When the password is blank we prompt for it at run
    time (getpass) and keep it only in memory. Filling it in enables unattended
    runs, at the cost of a plaintext secret in the (git-ignored) config file.
"""

from __future__ import annotations

import getpass

import pyodbc

from .. import config


def _resolve_credentials(sage: dict) -> tuple[str, str, str]:
    """Return (dsn, username, password), prompting for anything left blank."""
    dsn = sage.get("dsn", "").strip()
    if not dsn:
        raise ValueError("No Sage DSN configured. Set sage.dsn in config.json.")

    username = (sage.get("username") or "").strip()
    if not username:
        username = input("Sage username: ").strip()

    password = sage.get("password") or ""
    if not password:
        # Never stored on disk; typed each run and held only in memory.
        password = getpass.getpass(f"Sage password for {username}@{dsn}: ")

    return dsn, username, password


def open_connection(dsn: str, username: str, password: str,
                    timeout: int = 15) -> "pyodbc.Connection":
    """Open a read-only connection with explicit credentials (no prompting).

    Used by the API/desktop layer, which collects the password from the UI once
    and holds the live connection in memory. Never writes back to Sage.
    """
    if not (dsn or "").strip():
        raise ValueError("No Sage DSN provided.")
    conn_str = f"DSN={dsn};UID={username};PWD={password}"
    return pyodbc.connect(conn_str, readonly=True, timeout=timeout)


def connect(cfg: dict | None = None, timeout: int = 15) -> "pyodbc.Connection":
    """Open a read-only connection to the configured Sage DSN.

    Password is taken from config.json if present, otherwise prompted for and
    kept only in memory.
    """
    cfg = cfg or config.load()
    dsn, username, password = _resolve_credentials(cfg["sage"])
    return open_connection(dsn, username, password, timeout)


def query(conn: "pyodbc.Connection", sql: str) -> list[dict]:
    """Run a read-only SELECT, return rows as list[dict].

    No parameter binding is available: build `sql` with literal values already
    inlined (and escape single quotes in account refs via `quote_literal`).
    """
    cur = conn.cursor()
    cur.execute(sql)
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def quote_literal(value: str) -> str:
    """Escape a string for safe inlining into a WHERE clause (single quotes)."""
    return value.replace("'", "''")


def probe(conn: "pyodbc.Connection", table: str = "AUDIT_HEADER") -> dict:
    """Connectivity self-test: fetch column names + one sample row from `table`.

    Streams a single row (fetchmany) rather than loading the whole table, so it
    is safe on large audit tables. Returns {'columns': [...], 'sample': {...}|None}.
    """
    cur = conn.cursor()
    cur.execute(f"SELECT * FROM {table}")
    columns = [c[0] for c in cur.description]
    rows = cur.fetchmany(1)
    cur.close()
    sample = dict(zip(columns, rows[0])) if rows else None
    return {"columns": columns, "sample": sample}
