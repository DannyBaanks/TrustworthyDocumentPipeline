"""Local deterministic demo for the document pipeline."""
from __future__ import annotations

import argparse
import json

from .pipeline import DocumentPipeline, Extraction


class DemoDocumentService:
    name = "demo-document-service"

    def extract(self, document: bytes) -> Extraction:
        return Extraction(
            fields={"document_type": "demo", "bytes": len(document)},
            confidence=0.91,
        )


class DemoReviewer:
    def review(self, extraction: Extraction) -> bool:
        return extraction.confidence >= 0.5


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true")
    args = parser.parse_args()
    if not args.demo:
        parser.error("the initial CLI exposes only --demo")
    result = DocumentPipeline(DemoDocumentService(), DemoReviewer()).run(
        b"deterministic demo document"
    )
    print(json.dumps(result.to_dict(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
