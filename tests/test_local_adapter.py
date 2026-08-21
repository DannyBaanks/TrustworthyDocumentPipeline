"""Tests for the local heuristic extractor.

This adapter exists to prove a claim the README makes: that the evidence layer
does not depend on the extraction vendor. A second, deliberately weaker
extractor is a stronger proof than a second commercial API would be, because it
also shows what happens when the thing underneath gets *worse*.

It is not a competitor to DWS. It cannot read tables, it cannot score its own
confidence, and it says so.
"""
from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from trustdocs.local_adapter import LocalHeuristicAdapter, extract_fields_from_text
from trustdocs.pipeline import Document, DocumentPipeline
from trustdocs.validation import RequiredFieldsRule


class FieldExtractionTests(unittest.TestCase):
    """The text-to-fields step is pure, so it is tested without any PDF."""

    TEXT = """
    ACME Supplies Ltd
    Invoice Number: INV-2026-0042
    Issue Date: 2026-03-14
    Currency: USD
    Total Due: 1,234.56
    """

    def test_finds_an_invoice_number(self):
        fields = extract_fields_from_text(self.TEXT)
        self.assertEqual(fields["invoice_number"].value, "INV-2026-0042")

    def test_finds_and_parses_a_total(self):
        fields = extract_fields_from_text(self.TEXT)
        self.assertEqual(fields["total_amount"].value, 1234.56)
        self.assertIsInstance(fields["total_amount"].value, float)

    def test_reports_no_confidence_rather_than_inventing_one(self):
        """A regex has no calibrated confidence. Making one up would be a lie
        that propagates straight into the audit record."""
        for field in extract_fields_from_text(self.TEXT).values():
            self.assertIsNone(field.confidence)

    def test_provenance_records_how_the_value_was_found(self):
        fields = extract_fields_from_text(self.TEXT)
        provenance = fields["invoice_number"].provenance
        self.assertEqual(provenance["method"], "regex")
        self.assertIn("pattern", provenance)

    def test_a_document_with_nothing_recognisable_yields_no_fields(self):
        self.assertEqual(extract_fields_from_text("a poem about rain"), {})

    def test_does_not_claim_line_items_it_cannot_read(self):
        """The reconciliation rule is the project's headline check, and it must
        not appear to pass just because a weak extractor found no items."""
        self.assertNotIn("line_items", extract_fields_from_text(self.TEXT))


class LocalAdapterPipelineTests(unittest.TestCase):
    TEXT = "Invoice Number: INV-9\nTotal Due: 50.00\n"

    class _StubAdapter(LocalHeuristicAdapter):
        """Bypasses PDF parsing so the pipeline behaviour is what is tested."""

        def _text(self, document: Document) -> str:
            return document.content.decode("utf-8")

    def _document(self) -> Document:
        return Document(self.TEXT.encode("utf-8"), "invoice.pdf", "application/pdf")

    def test_absent_confidence_forces_human_review(self):
        """The safety property that falls out of admitting ignorance."""
        result = DocumentPipeline(self._StubAdapter(), _AlwaysApprove()).run(self._document())
        self.assertTrue(result.reviewed)
        self.assertEqual(result.status, "APPROVED_BY_HUMAN")
        self.assertNotEqual(result.status, "AUTO_APPROVED")

    def test_evidence_verifies_exactly_as_it_does_for_the_vendor_path(self):
        result = DocumentPipeline(self._StubAdapter(), _AlwaysApprove()).run(self._document())
        valid, errors = result.evidence.verify()
        self.assertTrue(valid, errors)

    def test_validation_rules_apply_unchanged(self):
        result = DocumentPipeline(
            self._StubAdapter(), _AlwaysApprove(),
            rules=(RequiredFieldsRule(("invoice_number", "total_amount", "vendor_name")),),
        ).run(self._document())
        failed = [f for f in result.validation if f.status == "FAIL"]
        self.assertTrue(failed)
        self.assertIn("vendor_name", failed[0].message)

    def test_the_operation_name_records_which_extractor_ran(self):
        """An audit record that does not say who extracted the fields cannot
        answer the question it exists to answer."""
        result = DocumentPipeline(self._StubAdapter(), _AlwaysApprove()).run(self._document())
        operations = [node.operation for node in result.evidence.nodes]
        self.assertIn("local-heuristic-extractor", operations)


class VendorIndependenceTests(unittest.TestCase):
    """The claim under test: swapping the extractor does not break the chain."""

    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.ledger = Path(self._tmp.name) / "ledger.jsonl"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_two_different_extractors_write_into_one_valid_chain(self):
        from trustdocs.cli import DemoDocumentService
        from trustdocs.ledger import Ledger, verify_ledger

        document = Document(b"Invoice Number: INV-1\nTotal Due: 10.00\n",
                            "invoice.pdf", "application/pdf")

        for service in (DemoDocumentService(), LocalAdapterPipelineTests._StubAdapter()):
            result = DocumentPipeline(service, _AlwaysApprove()).run(document)
            Ledger(self.ledger).append(
                execution_id=result.evidence.execution_id,
                record_sha256=result.evidence.record_sha256,
                document_sha256=result.document_sha256,
                decision=result.status)

        ok, errors = verify_ledger(self.ledger)
        self.assertTrue(ok, errors)
        self.assertEqual(len(Ledger(self.ledger).entries()), 2)

    def test_the_same_document_through_two_extractors_yields_different_evidence(self):
        """Same input, different extractor, different record -- as it must be.

        If the evidence were identical the record would not actually capture
        what produced the decision.
        """
        from trustdocs.cli import DemoDocumentService

        document = Document(b"Invoice Number: INV-1\nTotal Due: 10.00\n",
                            "invoice.pdf", "application/pdf")
        a = DocumentPipeline(DemoDocumentService(), _AlwaysApprove()).run(document)
        b = DocumentPipeline(LocalAdapterPipelineTests._StubAdapter(),
                             _AlwaysApprove()).run(document)

        self.assertEqual(a.document_sha256, b.document_sha256)
        self.assertNotEqual(a.evidence.record_sha256, b.evidence.record_sha256)
        self.assertTrue(a.evidence.verify()[0])
        self.assertTrue(b.evidence.verify()[0])


class _AlwaysApprove:
    def review(self, extraction) -> bool:
        return True


if __name__ == "__main__":
    unittest.main()
