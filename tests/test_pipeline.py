from __future__ import annotations

import unittest

from trustdocs.pipeline import Document, DocumentPipeline, Extraction, FieldValue


class Service:
    name = "test-service"

    def __init__(self, confidence: float) -> None:
        self.confidence = confidence
        self.calls = 0

    def extract(self, document: Document) -> Extraction:
        self.calls += 1
        return Extraction(
            {"size": FieldValue(len(document.content), self.confidence, {"source": "test"})},
            self.confidence,
        )


class Reviewer:
    def __init__(self, approved: bool) -> None:
        self.approved = approved
        self.calls = 0

    def review(self, extraction: Extraction) -> bool:
        self.calls += 1
        return self.approved


class PipelineTests(unittest.TestCase):
    def test_high_confidence_is_auto_approved(self) -> None:
        reviewer = Reviewer(False)
        result = DocumentPipeline(Service(0.95), reviewer).run(
            Document(b"doc", "doc.pdf", "application/pdf")
        )
        self.assertEqual(result.status, "AUTO_APPROVED")
        self.assertFalse(result.reviewed)
        self.assertEqual(reviewer.calls, 0)

    def test_low_confidence_requires_human_review(self) -> None:
        reviewer = Reviewer(True)
        result = DocumentPipeline(Service(0.40), reviewer).run(
            Document(b"doc", "doc.pdf", "application/pdf")
        )
        self.assertEqual(result.status, "APPROVED")
        self.assertTrue(result.reviewed)
        self.assertEqual(reviewer.calls, 1)
        self.assertEqual(len(result.evidence_sha256), 64)

    def test_rejected_review_is_preserved(self) -> None:
        result = DocumentPipeline(Service(0.20), Reviewer(False)).run(
            Document(b"doc", "doc.pdf", "application/pdf")
        )
        self.assertEqual(result.status, "REJECTED")
        self.assertFalse(result.approved)


if __name__ == "__main__":
    unittest.main()
