"""Official Nutrient Data Extraction API adapter.

The adapter is the only module that knows the Nutrient HTTP contract. The
pipeline receives normalized fields and never sees API keys or URLs.
"""
from __future__ import annotations

import json
import os
from typing import Any

import requests

from .pipeline import Extraction, FieldValue


class NutrientExtractionAdapter:
    name = "nutrient-data-extraction"

    def __init__(self, *, api_key: str | None = None,
                 endpoint: str = "https://api.nutrient.io/extraction/parse",
                 timeout_seconds: float = 60.0,
                 max_response_bytes: int = 20_000_000) -> None:
        self._api_key = api_key or os.environ.get("NUTRIENT_EXTRACTION_API_KEY")
        if not self._api_key:
            raise ValueError("NUTRIENT_EXTRACTION_API_KEY is required")
        if not endpoint.startswith("https://"):
            raise ValueError("Nutrient endpoint must use HTTPS")
        if timeout_seconds <= 0 or max_response_bytes <= 0:
            raise ValueError("timeout and response limit must be positive")
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds
        self.max_response_bytes = max_response_bytes

    def extract(self, document: bytes) -> Extraction:
        instructions = json.dumps({
            "mode": "structure",
            "output": {"format": "spatial"},
        })
        response = requests.post(
            self.endpoint,
            headers={"Authorization": f"Bearer {self._api_key}"},
            files={"file": ("document.pdf", document, "application/pdf")},
            data={"instructions": instructions},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        if len(response.content) > self.max_response_bytes:
            raise ValueError("Nutrient response exceeds configured limit")
        return self._normalize(response.json())

    @staticmethod
    def _normalize(payload: dict[str, Any]) -> Extraction:
        output = payload.get("output")
        if not isinstance(output, dict):
            raise ValueError("Nutrient response has no output object")
        elements = output.get("elements")
        if not isinstance(elements, list):
            raise ValueError("Nutrient response has no spatial elements")

        fields: dict[str, FieldValue] = {}
        for element_index, element in enumerate(elements):
            if not isinstance(element, dict):
                continue
            if element.get("type") == "keyValueRegion":
                for pair_index, pair in enumerate(element.get("pairs", [])):
                    if not isinstance(pair, dict):
                        continue
                    key = pair.get("key", {})
                    value = pair.get("value", {})
                    name = str(key.get("value", "")).strip()
                    if not name:
                        continue
                    fields[name] = FieldValue(
                        value=value.get("value"),
                        confidence=value.get("confidence"),
                        provenance={
                            "element_index": element_index,
                            "pair_index": pair_index,
                            "page": value.get("page", element.get("page")),
                            "bounds": value.get("bounds"),
                            "source": "nutrient-spatial-json",
                        },
                    )
            elif element.get("type") == "table":
                table_id = str(element.get("id", f"table_{element_index}"))
                fields[table_id] = FieldValue(
                    value=element.get("cells", []),
                    confidence=element.get("confidence"),
                    provenance={
                        "element_index": element_index,
                        "page": element.get("page"),
                        "bounds": element.get("bounds"),
                        "source": "nutrient-spatial-json",
                    },
                )

        # The documented spatial response exposes per-element confidence, not
        # a single document confidence. The pipeline therefore routes this
        # result to review rather than inventing an aggregate score.
        return Extraction(fields=fields, document_confidence=None)
