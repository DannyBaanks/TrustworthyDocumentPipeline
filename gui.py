"""Launch the Trustworthy Document Pipeline GUI.

Usage:
    python gui.py
"""
import sys
import os

# Ensure src/ is on the path so trustdocs is importable without pip install -e
_src = os.path.join(os.path.dirname(__file__), "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from trustdocs.gui import main

raise SystemExit(main())
