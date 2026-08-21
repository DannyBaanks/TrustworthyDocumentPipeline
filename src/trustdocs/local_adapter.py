"""A deliberately weak local extractor, for showing what the evidence layer is.

The README claims the evidence layer is independent of the extraction vendor.
This adapter is that claim as code: a second extractor, sharing nothing with the
DWS path except the `DocumentService` protocol, whose output flows through the
same validation, the same confidence gate, the same evidence chain and the same
ledger.

It is intentionally worse than the service it sits beside. It reads text with a
handful of regexes, it cannot see tables, and — the important part — **it has no
calibrated confidence to report**, so it reports none.

That is not a gap to be patched with a plausible-looking number. It is the
behaviour worth demonstrating: when the extractor cannot say how sure it is, the
pipeline's existing policy routes every document to a human. The system degrades
into caution rather than into confident nonsense, and that property was already
in the pipeline before this file existed.

Requires the `local` extra (`pip install -e ".[local]"`) for PDF text.
"""
from __future__ import annotations

import re
from typing import Dict

from .pipeline import Document, Extraction, FieldValue

OPERATION = "local-heuristic-extractor"

# Ordered: the first pattern that matches a field wins. Each carries its own
# name so the evidence can record which one produced the value.
PATTERNS: tuple[tuple[str, str, str], ...] = (
    ("invoice_number", r"invoice\s*(?:number|no\.?|#)\s*[:\-]?\s*([A-Z0-9][A-Z0-9\-/]{2,})",
     "invoice-number-labelled"),
    ("total_amount", r"(?:total\s*(?:due|amount)?|amount\s*due)\s*[:\-]?\s*"
                     r"[$€£]?\s*([0-9][0-9,]*\.?[0-9]{0,2})", "total-labelled"),
    ("issue_date", r"(?:issue\s*date|date\s*of\s*issue|invoice\s*date)\s*[:\-]?\s*"
                   r"(\d{4}-\d{2}-\d{2})", "issue-date-iso"),
    ("currency", r"\bcurrency\s*[:\-]?\s*([A-Z]{3})\b", "currency-labelled"),
)

_NUMERIC_FIELDS = {"total_amount"}


def _to_number(raw: str) -> float | None:
    try:
        return float(raw.replace(",", ""))
    except ValueError:
        return None


def extract_fields_from_text(text: str) -> Dict[str, FieldValue]:
    """Pull known fields out of plain text.

    Pure and PDF-free so it can be tested directly. Every value carries
    provenance naming the pattern that found it, because an audit record that
    cannot say *how* a value was obtained is not much of an audit record.

    Confidence is always `None`. A regex either matched or it did not; there is
    no probability behind it, and inventing one would put a fabricated number
    into the evidence chain.
    """
    fields: Dict[str, FieldValue] = {}
    for name, pattern, pattern_id in PATTERNS:
        if name in fields:
            continue
        match = re.search(pattern, text, re.IGNORECASE)
        if not match:
            continue
        raw = match.group(1).strip()
        value: object = raw
        if name in _NUMERIC_FIELDS:
            parsed = _to_number(raw)
            if parsed is None:
                continue
            value = parsed
        fields[name] = FieldValue(
            value=value,
            confidence=None,
            provenance={"method": "regex", "pattern": pattern_id, "extractor": OPERATION},
        )
    return fields


class LocalHeuristicAdapter:
    """A `DocumentService` that needs no network, no key and no account."""

    name = OPERATION

    def _text(self, document: Document) -> str:
        """Extract text from the document bytes.

        Isolated so tests can substitute plain text, and so the optional
        dependency is only required when a real PDF is processed.
        """
        try:
            from pypdf import PdfReader
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise RuntimeError(
                "the local extractor needs pypdf: pip install -e \".[local]\""
            ) from exc

        import io

        reader = PdfReader(io.BytesIO(document.content))
        return "\n".join(page.extract_text() or "" for page in reader.pages)

    def extract(self, document: Document) -> Extraction:
        fields = extract_fields_from_text(self._text(document))
        # No document-level confidence: see the module docstring. The pipeline
        # reads None as "unknown" and sends the document to a human.
        return Extraction(fields=fields, document_confidence=None)
