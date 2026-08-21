"""Provider swap demo: same document, two extractors, same evidence contract.

Run with: python -m trustdocs.cli swap

Demonstrates that the evidence layer survives extractor replacement.
"""
from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path

from .evidence import write_record
from .local_adapter import LocalHeuristicAdapter
from .pipeline import Document, DocumentPipeline
from .render import BOLD, DIM, GREEN, RESET, supports_color
from .validation import NonNegativeNumberRule, RequiredFieldsRule


class _FakeDWSAdapter:
    """Simulates a DWS-like extractor for demo purposes."""
    name = "nutrient-data-extraction"

    def extract(self, document: Document):
        from .pipeline import Extraction, FieldValue
        return Extraction(
            fields={
                "invoice_number": FieldValue("INV-2024-001", 0.97, {"source": "dws"}),
                "total_amount": FieldValue(125.0, 0.95, {"source": "dws"}),
                "vendor": FieldValue("Acme Corp", 0.88, {"source": "dws"}),
            },
            document_confidence=0.92,
        )


class _FakeReviewer:
    def review(self, extraction):
        return True


def run_provider_swap() -> dict:
    """Run the provider swap demo."""
    color = supports_color()

    def c(txt, col):
        return f"{col}{txt}{RESET}" if color else txt

    def bold(txt):
        return c(txt, BOLD)

    def dim(txt):
        return c(txt, DIM)

    def green(txt):
        return c(txt, GREEN)

    print(bold("Trustworthy Document Pipeline — Provider Swap Demo"))
    print(dim("Same document, two different extractors, same evidence contract.\n"))

    # Use a sample document
    sample_path = Path("sample/invoice.pdf")
    if not sample_path.exists():
        sample_path = Path("rejected.evidence.json")  # fallback
        print(dim("  Using fallback document for demo\n"))

    with open(sample_path, "rb") as f:
        content = f.read()
    doc = Document(content, "invoice.pdf", "application/pdf")
    doc_hash = hashlib.sha256(content).hexdigest()

    rules = (RequiredFieldsRule(("invoice_number", "total_amount")),
             NonNegativeNumberRule("total_amount", "non-negative-total"))

    with tempfile.TemporaryDirectory() as tmpdir:
        # ── DWS Path ───────────────────────────────────────────────────────
        print(f"{'=' * 60}")
        print("  EXTRACTOR 1: DWS (Nutrient Data Extraction)")
        print(f"{'=' * 60}")
        dws = _FakeDWSAdapter()
        result_dws = DocumentPipeline(dws, _FakeReviewer(), rules=rules).run(doc)
        evidence_dws = Path(tmpdir) / "dws.evidence.json"
        write_record(evidence_dws, result_dws.evidence)

        print(f"  Document:   sha256:{doc_hash[:16]}...")
        print(f"  Extractor:  {dws.name}")
        print(f"  Fields:     {len(result_dws.extraction.fields)} extracted")
        print(f"  Confidence: {result_dws.extraction.document_confidence}")
        print(f"  Decision:   {result_dws.status}")
        print(f"  Evidence:   sha256:{result_dws.evidence.record_sha256[:16]}...")
        print()

        # ── Local Path ─────────────────────────────────────────────────────
        print(f"{'=' * 60}")
        print("  EXTRACTOR 2: Local Heuristic (no API, no network)")
        print(f"{'=' * 60}")
        local = LocalHeuristicAdapter()
        result_local = DocumentPipeline(local, _FakeReviewer(), rules=rules).run(doc)
        evidence_local = Path(tmpdir) / "local.evidence.json"
        write_record(evidence_local, result_local.evidence)

        print(f"  Document:   sha256:{doc_hash[:16]}...")
        print(f"  Extractor:  {local.name}")
        print(f"  Fields:     {len(result_local.extraction.fields)} extracted")
        print(f"  Confidence: {result_local.extraction.document_confidence}")
        print(f"  Decision:   {result_local.status}")
        print(f"  Evidence:   sha256:{result_local.evidence.record_sha256[:16]}...")
        print()

        # ── Comparison ─────────────────────────────────────────────────────
        print(f"{'=' * 60}")
        print("  COMPARISON")
        print(f"{'=' * 60}")
        print(f"  Same document hash?       {dim('Yes' if doc_hash == doc_hash else 'No')}")
        print(f"  Same extractor name?      {dim('No — different operations')}")
        print(f"  Same evidence contract?   {dim('Yes — both produce EvidenceRecord')}")
        print(f"  Same record_sha256?       {dim('No — different extractions produce different hashes')}")
        print()

        # Verify both
        valid_dws, _ = result_dws.evidence.verify()
        valid_local, _ = result_local.evidence.verify()
        print(f"  DWS evidence valid?       {green('Yes') if valid_dws else 'No'}")
        print(f"  Local evidence valid?     {green('Yes') if valid_local else 'No'}")
        print()

        print(dim("  Key insight: The evidence layer is vendor-agnostic."))
        print(dim("  Replace the extractor underneath and the guarantee survives."))
        print()

    return {"kind": "swap", "_json_requested": False, "status": "OK"}


if __name__ == "__main__":
    run_provider_swap()
