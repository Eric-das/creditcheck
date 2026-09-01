"""PyInstaller entry point for the CreditCheck desktop app.

Kept at the repo root (outside the src package) so PyInstaller has a single
script to bundle; it just delegates to the package's desktop launcher.
"""
from creditcheck.desktop import main

if __name__ == "__main__":
    main()
