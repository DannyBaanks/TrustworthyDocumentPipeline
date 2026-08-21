from __future__ import annotations

import os
import unittest
from unittest.mock import Mock, patch

from trustdocs.nutrient_adapter import NutrientExtractionAdapter
from trustdocs.pipeline import Document


class NutrientAdapterTests(unittest.TestCase):
    def test_normalizes_key_values_and_tables_without_aggregate_confidence(self) -> None:
        result = NutrientExtractionAdapter._normalize({
            "output": {
                "data": {"invoice_number": "INV-1", "total_amount": 10},
                "metadata": {
                    "invoice_number": {"confidence": 0.98, "pageNumber": 1},
                    "total_amount": {"confidence": 0.91, "pageNumber": 1},
                },
            }
        })
        self.assertEqual(result.fields["invoice_number"].value, "INV-1")
        self.assertEqual(result.fields["invoice_number"].confidence, 0.98)
        self.assertEqual(result.fields["total_amount"].confidence, 0.91)
        self.assertIsNone(result.document_confidence)

    @patch.dict(os.environ, {}, clear=True)
    def test_requires_api_key_without_network_call(self) -> None:
        """The environment is cleared on purpose.

        Without this the test passed in CI (no key present) and failed on any
        developer machine with NUTRIENT_EXTRACTION_API_KEY exported, because the
        constructor falls back to the environment when given an empty key. A
        test whose result depends on who runs it proves nothing.
        """
        with self.assertRaises(ValueError):
            NutrientExtractionAdapter(api_key="")

    @patch.dict(os.environ, {"NUTRIENT_EXTRACTION_API_KEY": "from-env"}, clear=True)
    def test_falls_back_to_the_environment_when_no_key_is_passed(self) -> None:
        """The fallback is deliberate behaviour, so it gets its own test."""
        adapter = NutrientExtractionAdapter()
        self.assertEqual(adapter._api_key, "from-env")

    @patch("trustdocs.nutrient_adapter.requests.post")
    def test_preserves_filename_and_media_type(self, post: Mock) -> None:
        response = Mock()
        response.content = b'{}'
        response.json.return_value = {"output": {"data": {}, "metadata": {}}}
        post.return_value = response
        adapter = NutrientExtractionAdapter(api_key="test-key")
        adapter.extract(Document(b"png", "scan.png", "image/png"))
        files = post.call_args.kwargs["files"]
        self.assertEqual(files["file"][0], "scan.png")
        self.assertEqual(files["file"][2], "image/png")


if __name__ == "__main__":
    unittest.main()
