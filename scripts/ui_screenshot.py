#!/usr/bin/env python3
"""Headless UI screenshot tool for the Remote SSH Desktop client.

Boots ``MainWindow`` with the offscreen Qt platform and saves a PNG via
``QWidget.grab()`` so the layout can be inspected without a real display.

Examples
--------
Single screenshot at a fixed size::

    QT_QPA_PLATFORM=offscreen python scripts/ui_screenshot.py --out artifacts/ui_main.png --size 1400x1000

All three reference widths (1100 / 1400 / 1920) into a directory::

    QT_QPA_PLATFORM=offscreen python scripts/ui_screenshot.py --widths 1100,1400,1920 --outdir artifacts

Both themes at once::

    QT_QPA_PLATFORM=offscreen python scripts/ui_screenshot.py --widths 1100,1400,1920 --theme dark
    QT_QPA_PLATFORM=offscreen python scripts/ui_screenshot.py --widths 1100,1400,1920 --theme light

If the offscreen platform yields a blank image on your system, run under Xvfb::

    xvfb-run -a python scripts/ui_screenshot.py --out artifacts/ui_main.png --size 1400x1000
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Default to the offscreen platform so this works without a display server.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Make the package importable when run from the repo root or elsewhere.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtWidgets import QApplication  # noqa: E402

from remote_ssh_desktop.client.main import MainWindow, apply_theme  # noqa: E402


def parse_size(text: str) -> tuple[int, int]:
    width, height = text.lower().replace(" ", "").split("x", 1)
    return int(width), int(height)


def settle(app: QApplication, rounds: int = 5) -> None:
    """Pump the event loop so deferred layout/styling is applied before grab()."""
    for _ in range(rounds):
        app.processEvents()


def capture(window: MainWindow, app: QApplication, out: Path, size: tuple[int, int]) -> bool:
    width, height = size
    window.resize(width, height)
    window.show()
    settle(app)
    out.parent.mkdir(parents=True, exist_ok=True)
    pixmap = window.grab()
    ok = pixmap.save(str(out))
    print(f"{'saved' if ok else 'FAILED'}: {out}  ({pixmap.width()}x{pixmap.height()})")
    return ok


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture MainWindow screenshots headless")
    parser.add_argument("--out", default="artifacts/ui_main.png", help="output PNG path (single mode)")
    parser.add_argument("--size", default="1400x1000", help="WxH for single mode, e.g. 1400x1000")
    parser.add_argument("--outdir", default="artifacts", help="output directory (multi-width mode)")
    parser.add_argument("--widths", default="", help="comma-separated widths, e.g. 1100,1400,1920")
    parser.add_argument("--height", type=int, default=1000, help="window height for multi-width mode")
    parser.add_argument("--theme", default="dark", choices=["dark", "light"], help="QSS theme")
    args = parser.parse_args()

    app = QApplication.instance() or QApplication(sys.argv[:1])
    apply_theme(app, args.theme)
    window = MainWindow()

    ok = True
    if args.widths.strip():
        outdir = Path(args.outdir)
        for raw in args.widths.split(","):
            raw = raw.strip()
            if not raw:
                continue
            width = int(raw)
            out = outdir / f"ui_{args.theme}_{width}.png"
            ok = capture(window, app, out, (width, args.height)) and ok
    else:
        ok = capture(window, app, Path(args.out), parse_size(args.size))

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
