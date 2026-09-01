"""Local HTTP API that exposes the CreditCheck engine to the desktop UI.

Runs on localhost only, inside the same process as the pywebview window. The
engine stays read-only; this layer just serves its JSON to the front end.
"""
