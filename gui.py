"""Launch the Trustworthy Document Pipeline GUI.

Usage:
    python gui.py
"""
import os
import sys

# Ensure src/ is on the path so trustdocs is importable without pip install -e
_src = os.path.join(os.path.dirname(__file__), "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

# E402 a proposito: este import tiene que ocurrir DESPUES de insertar src/ en
# sys.path, o el lanzador falla cuando el paquete no esta instalado con pip -e.
from trustdocs.gui import main  # noqa: E402

raise SystemExit(main())
