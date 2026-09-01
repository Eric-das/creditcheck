# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller one-file build for the CreditCheck desktop app.

Bundles Python + FastAPI/uvicorn + pywebview (+ the .NET/EdgeChromium bits) and
the web assets into a single CreditCheck.exe. The target PC still needs Sage 50
(for the ODBC driver) and a DSN pointing at its company data.
"""
from PyInstaller.utils.hooks import collect_submodules, collect_all

datas = [("src/creditcheck/api/web", "creditcheck/api/web")]
binaries = []
# uvicorn imports its loop/protocol/lifespan implementations dynamically.
hiddenimports = collect_submodules("uvicorn") + [
    "webview.platforms.winforms",
    "webview.platforms.edgechromium",
]
# pywebview + the pythonnet/clr runtime it uses on Windows.
for pkg in ("webview", "clr_loader", "pythonnet"):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass

a = Analysis(
    ["run_app.py"],
    pathex=["src"],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="CreditCheck",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,
    icon="assets/creditcheck.ico",
)
