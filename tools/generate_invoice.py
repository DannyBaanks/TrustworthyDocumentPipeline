"""Generate the synthetic invoice fixture used by the demo and live test.

The fixture is deterministic, contains fictional data only, and is
regenerated with this script so judges can inspect exactly what Nutrient
receives.

Usage:
    python tools/generate_invoice.py sample/invoice.pdf
"""
from __future__ import annotations

import sys
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas


def generate_invoice(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pdf = canvas.Canvas(str(path), pagesize=letter)
    width, _height = letter
    left = 1.0 * inch

    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawString(left, 10.4 * inch, "Acme Supply Co.")
    pdf.setFont("Helvetica", 10)
    pdf.drawString(left, 10.1 * inch, "742 Evergreen Terrace, Springfield")
    pdf.drawString(left, 9.9 * inch, "contact@acme-supply.example")
    pdf.drawString(left, 9.7 * inch, "INV-2026-0012")
    pdf.drawString(left, 9.5 * inch, "Issue date: 2026-07-14")
    pdf.drawString(left, 9.3 * inch, "Currency: USD")

    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(left, 8.8 * inch, "Line items")
    rows = [
        ("Description", "Qty", "Unit price", "Total"),
        ("Industrial grade fasteners, M8", "4", "12.50", "50.00"),
        ("Galvanized steel bolts, 60 mm", "6", "3.75", "22.50"),
        ("Threaded rods, 1 m", "2", "8.90", "17.80"),
    ]
    y = 8.4 * inch
    pdf.setFont("Helvetica", 10)
    for row in rows:
        x = left
        for cell in row:
            pdf.drawString(x, y, cell)
            x += 1.7 * inch
        y -= 0.25 * inch

    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(left, y - 0.2 * inch, "Subtotal: 90.30")
    pdf.drawString(left, y - 0.4 * inch, "Tax (18%): 16.25")
    pdf.drawString(left, y - 0.6 * inch, "Total amount: 106.55")

    pdf.save()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: python tools/generate_invoice.py <output.pdf>")
    generate_invoice(Path(sys.argv[1]))
    print(f"wrote {sys.argv[1]}")
