from __future__ import annotations

import unittest

from trustdocs.cli import DemoReviewer, WarningDemoDocumentService
from trustdocs.pipeline import Document, DocumentPipeline
from trustdocs.validation import ConfidenceWarningRule


class WarningDemoTests(unittest.TestCase):
    def test_warning_routes_to_human_approval(self) -> None:
        result = DocumentPipeline(
            WarningDemoDocumentService(), DemoReviewer(),
            rules=(ConfidenceWarningRule("total_amount", 0.85, "low-total-confidence"),),
        ).run(Document(b"warning", "warning.pdf", "application/pdf"))
        self.assertEqual(result.validation[0].status, "WARNING")
        self.assertEqual(result.status, "APPROVED_BY_HUMAN")
        self.assertTrue(result.reviewed)


if __name__ == "__main__":
    unittest.main()
