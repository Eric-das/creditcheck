"""Desktop entry point.

Starts the FastAPI app on a private localhost port in a background thread, then
opens a native window (WebView2 on Windows) pointing at it. Everything runs in
one process on this PC; nothing is served to the network.

    python -m creditcheck.desktop
"""
from __future__ import annotations

import socket
import threading
import time

import uvicorn
import webview

from .api.app import app


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _wait_until_up(port: int, timeout: float = 15.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.1)


def main() -> None:
    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    # uvicorn skips signal handlers off the main thread, so this is safe.
    threading.Thread(target=server.run, daemon=True).start()
    _wait_until_up(port)

    webview.create_window(
        "CreditCheck — Forensic AR credit control",
        f"http://127.0.0.1:{port}/",
        width=1180, height=820, min_size=(960, 640),
    )
    webview.start()


if __name__ == "__main__":
    main()
