from __future__ import annotations

import unittest

from trustdocs.nutrient_adapter import NutrientExtractionAdapter


class NutrientAdapterTests(unittest.TestCase):
    def test_normalizes_key_values_and_tables_without_aggregate_confidence(self) -> None:
        result = NutrientExtractionAdapter._normalize({
            "output": {
                "elements": [
                    {
                        "type": "keyValueRegion",
                        "page": {"pageNumber": 1},
                        "pairs": [{
                            "key": {"value": "Invoice number"},
                            "value": {
                                "value": "INV-1",
                                "confidence": 0.98,
                                "bounds": {"x": 1},
                            },
                        }],
                    },
                    {
                        "type": "table",
                        "id": "items",
                        "confidence": 0.91,
                        "cells": [{"row": 0, "column": 0, "text": "Total"}],
                    },
                ]
            }
        })
        self.assertEqual(result.fields["Invoice number"].value, "INV-1")
        self.assertEqual(result.fields["Invoice number"].confidence, 0.98)
        self.assertEqual(result.fields["items"].confidence, 0.91)
        self.assertIsNone(result.document_confidence)

    def test_requires_api_key_without_network_call(self) -> None:
        with self.assertRaises(ValueError):
            NutrientExtractionAdapter(api_key="")


if __name__ == "__main__":
    unittest.main()
