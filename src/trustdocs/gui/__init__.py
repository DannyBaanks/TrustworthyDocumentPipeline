"""Trustworthy Document Pipeline — GUI entry point.

Run with: python -m trustdocs.gui
"""
from __future__ import annotations

import sys


def main() -> int:
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print("PySide6 is required for the GUI.")
        print("Install with: pip install 'trustworthy-document-pipeline[gui]'")
        return 1

    from .main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("Trustworthy Document Pipeline")
    app.setStyle("Fusion")

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
