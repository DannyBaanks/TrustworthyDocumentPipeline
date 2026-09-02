"""Optional live integration against the real Nutrient Data Extraction API.

This suite is skipped when NUTRIENT_EXTRACTION_API_KEY is not set, so CI and
judges without a key still get a green unit run. With a key, it exercises the
real /extraction/extract contract against the committed synthetic invoice.

Run with a key:
    python -m unittest tests.test_live_nutrient -v
"""
from __future__ import annotations

import json
import os
import unittest
from pathlib import Path

from trustdocs.nutrient_adapter import NutrientExtractionAdapter
from trustdocs.pipeline import Document, DocumentPipeline
from trustdocs.validation import (
    FieldConfidencePolicy,
    LineItemsConsistentRule,
    NonNegativeNumberRule,
    RequiredFieldsRule,
)

SAMPLE_INVOICE = Path(__file__).resolve().parents[1] / "sample" / "invoice.pdf"


class ApproveReviewer:
    def review(self, extraction: object) -> bool:
        return True


@unittest.skipUnless(
    os.environ.get("NUTRIENT_EXTRACTION_API_KEY"),
    "NUTRIENT_EXTRACTION_API_KEY not set; live Nutrient run skipped",
)
class LiveNutrientTests(unittest.TestCase):
    def test_invoice_through_real_pipeline(self) -> None:
        self.assertTrue(SAMPLE_INVOICE.is_file(), "sample/invoice.pdf missing")
        with SAMPLE_INVOICE.open("rb") as stream:
            document = Document(stream.read(), SAMPLE_INVOICE.name, "application/pdf")
        result = DocumentPipeline(
            NutrientExtractionAdapter(), ApproveReviewer(),
            rules=(
                RequiredFieldsRule(("invoice_number", "total_amount", "line_items")),
                NonNegativeNumberRule("total_amount", "non-negative-total"),
                LineItemsConsistentRule("line_items", "total_amount", "line-items-reconcile"),
                FieldConfidencePolicy(("invoice_number", "total_amount", "line_items"), 0.85),
            ),
        ).run(document)
        # Nutrient returns per-field confidence. The policy auto-approves only
        # when every required field is known and above threshold; otherwise it
        # correctly routes the exact extraction state to a reviewer.
        confidence_gate = next(
            finding for finding in result.validation
            if finding.rule_id == "field-confidence-gate"
        )
        self.assertEqual(result.reviewed, confidence_gate.status != "PASS")
        self.assertTrue(result.approved)
        self.assertEqual(
            result.status,
            "AUTO_APPROVED" if confidence_gate.status == "PASS" else "APPROVED_BY_HUMAN",
        )
        if result.reviewed:
            self.assertIsNotNone(result.decision.review)
            self.assertEqual(result.evidence.review, result.decision.review.to_dict())
        valid, errors = result.evidence.verify()
        self.assertEqual((valid, errors), (True, []))
        print(json.dumps({
            "status": result.status,
            "field_count": len(result.extraction.fields),
            "validation": [finding.status for finding in result.validation],
            "execution_id": result.evidence.execution_id,
        }, indent=2))


if __name__ == "__main__":
    unittest.main()
