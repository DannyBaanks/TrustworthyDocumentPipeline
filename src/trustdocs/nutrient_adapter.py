"""Official Nutrient Data Extraction API adapter.

The adapter is the only module that knows the Nutrient HTTP contract. The
pipeline receives normalized fields and never sees API keys or URLs.
"""
from __future__ import annotations

import json
import os
from typing import Any

import requests

from .pipeline import Document, Extraction, FieldValue


class NutrientExtractionAdapter:
    name = "nutrient-data-extraction"

    def __init__(self, *, api_key: str | None = None,
                 endpoint: str = "https://api.nutrient.io/extraction/extract",
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

    def extract(self, document: Document) -> Extraction:
        instructions = json.dumps({
            "schema": {
                "type": "object",
                "properties": {
                    "vendor_name": {"type": "string"},
                    "invoice_number": {"type": "string"},
                    "issue_date": {"type": "string"},
                    "currency": {"type": "string"},
                    "total_amount": {"type": "number"},
                    "line_items": {"type": "array"},
                },
            },
            "parseConfig": {"mode": "structure"},
            "options": {"includeCitations": True},
        })
        response = requests.post(
            self.endpoint,
            headers={"Authorization": f"Bearer {self._api_key}"},
            files={"file": (document.filename, document.content, document.media_type)},
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
        data = output.get("data")
        metadata = output.get("metadata", {})
        if not isinstance(data, dict):
            raise ValueError("Nutrient response has no extracted data object")
        fields = {
            name: FieldValue(
                value=value,
                confidence=(metadata.get(name) or {}).get("confidence")
                if isinstance(metadata.get(name), dict) else None,
                provenance={
                    "citation": metadata.get(name),
                    "source": "nutrient-extract-json",
                },
            )
            for name, value in data.items()
        }

        # The documented extract response exposes per-field confidence, not
        # a single document confidence. Never invent an aggregate score.
        return Extraction(fields=fields, document_confidence=None)
