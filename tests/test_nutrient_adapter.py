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

    @patch("trustdocs.nutrient_adapter.requests.post")
    def test_http_error_raises_runtime_error_with_detail(self, post: Mock) -> None:
        response = Mock()
        response.ok = False
        response.status_code = 401
        response.content = b'{"requestId":"r1","errorMessage":"unauthorized","errorDetails":"bad key"}'
        response.json.return_value = {"requestId": "r1", "errorMessage": "unauthorized",
                                      "errorDetails": "bad key"}
        post.return_value = response
        adapter = NutrientExtractionAdapter(api_key="k")
        with self.assertRaises(RuntimeError) as ctx:
            adapter.extract(Document(b"data", "x.pdf", "application/pdf"))
        self.assertIn("401", str(ctx.exception))
        self.assertIn("unauthorized", str(ctx.exception))

    @patch("trustdocs.nutrient_adapter.requests.post")
    def test_http_error_with_non_json_body_falls_back_to_invalid_error(self, post: Mock) -> None:
        response = Mock()
        response.ok = False
        response.status_code = 500
        response.content = b'<html>Server Error</html>'
        response.json.side_effect = ValueError("not json")
        post.return_value = response
        adapter = NutrientExtractionAdapter(api_key="k")
        with self.assertRaises(RuntimeError) as ctx:
            adapter.extract(Document(b"data", "x.pdf", "application/pdf"))
        self.assertIn("invalid error response", str(ctx.exception))

    @patch("trustdocs.nutrient_adapter.requests.post")
    def test_oversize_response_raises_value_error(self, post: Mock) -> None:
        response = Mock()
        response.ok = True
        response.content = b"x" * 100
        response.json.return_value = {"output": {"data": {}, "metadata": {}}}
        post.return_value = response
        adapter = NutrientExtractionAdapter(api_key="k", max_response_bytes=10)
        with self.assertRaises(ValueError) as ctx:
            adapter.extract(Document(b"data", "x.pdf", "application/pdf"))
        self.assertIn("exceeds", str(ctx.exception))

    def test_non_https_endpoint_rejected(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            NutrientExtractionAdapter(api_key="k", endpoint="http://api.nutrient.io/")
        self.assertIn("HTTPS", str(ctx.exception))

    def test_non_positive_timeout_rejected(self) -> None:
        with self.assertRaises(ValueError):
            NutrientExtractionAdapter(api_key="k", timeout_seconds=0)
        with self.assertRaises(ValueError):
            NutrientExtractionAdapter(api_key="k", timeout_seconds=-1)

    def test_non_positive_max_response_bytes_rejected(self) -> None:
        with self.assertRaises(ValueError):
            NutrientExtractionAdapter(api_key="k", max_response_bytes=0)
        with self.assertRaises(ValueError):
            NutrientExtractionAdapter(api_key="k", max_response_bytes=-1)

    def test_normalize_without_output_raises(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            NutrientExtractionAdapter._normalize({"output": "wrong"})
        self.assertIn("output", str(ctx.exception))

    def test_normalize_without_data_raises(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            NutrientExtractionAdapter._normalize({"output": {"metadata": {}}})
        self.assertIn("extracted data", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
