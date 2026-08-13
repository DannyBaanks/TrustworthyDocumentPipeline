from __future__ import annotations

import unittest

from trustdocs.cli import DemoReviewer, InconsistentDemoDocumentService
from trustdocs.pipeline import Document, DocumentPipeline
from trustdocs.validation import LineItemsConsistentRule


class InconsistentDemoTests(unittest.TestCase):
    def test_arithmetic_mismatch_fails_validation_and_routes_to_human(self) -> None:
        result = DocumentPipeline(
            InconsistentDemoDocumentService(), DemoReviewer(),
            rules=(LineItemsConsistentRule("line_items", "total_amount", "line-items-reconcile"),),
        ).run(Document(b"inconsistent", "inconsistent.pdf", "application/pdf"))
        self.assertEqual(result.validation[0].status, "FAIL")
        self.assertEqual(result.validation[0].rule_id, "line-items-reconcile")
        self.assertTrue(result.reviewed)
        self.assertEqual(result.status, "APPROVED_BY_HUMAN")

    def test_consistent_line_items_pass(self) -> None:
        from trustdocs.pipeline import Extraction, FieldValue

        class ConsistentService:
            name = "consistent-demo"

            def extract(self, document: Document) -> Extraction:
                return Extraction(
                    fields={
                        "total_amount": FieldValue(65.0, 0.98, {"source": "demo"}),
                        "line_items": FieldValue([
                            {"description": "A", "quantity": 2, "unit_price": 10.0, "total": 20.0},
                            {"description": "B", "quantity": 3, "unit_price": 15.0, "total": 45.0},
                        ], 0.98, {"source": "demo"}),
                    },
                    document_confidence=0.95,
                )

        result = DocumentPipeline(
            ConsistentService(), DemoReviewer(),
            rules=(LineItemsConsistentRule("line_items", "total_amount", "line-items-reconcile"),),
        ).run(Document(b"consistent", "consistent.pdf", "application/pdf"))
        self.assertEqual(result.validation[0].status, "PASS")
        self.assertEqual(result.status, "AUTO_APPROVED")
        self.assertFalse(result.reviewed)


if __name__ == "__main__":
    unittest.main()
