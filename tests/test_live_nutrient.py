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
from trustdocs.validation import NonNegativeNumberRule, RequiredFieldsRule

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
                RequiredFieldsRule(("invoice_number", "total_amount")),
                NonNegativeNumberRule("total_amount", "non-negative-total"),
            ),
        ).run(document)
        # The real path has no aggregate document confidence, so the human
        # review gate always runs; a valid invoice is then approved.
        self.assertTrue(result.reviewed)
        self.assertTrue(result.approved)
        self.assertEqual(result.status, "APPROVED_BY_HUMAN")
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
