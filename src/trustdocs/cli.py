"""Local deterministic demo for the document pipeline."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .pipeline import DocumentPipeline, Extraction, FieldValue
from .nutrient_adapter import NutrientExtractionAdapter


class DemoDocumentService:
    name = "demo-document-service"

    def extract(self, document: bytes) -> Extraction:
        return Extraction(
            fields={
                "document_type": FieldValue("demo", 0.99, {"source": "demo"}),
                "bytes": FieldValue(len(document), 1.0, {"source": "demo"}),
            },
            document_confidence=0.91,
        )


class DemoReviewer:
    def review(self, extraction: Extraction) -> bool:
        return (extraction.document_confidence or 0) >= 0.5


class ConsoleReviewer:
    def __init__(self, approve: bool) -> None:
        self.approve = approve

    def review(self, extraction: Extraction) -> bool:
        # Do not print extracted values: they may contain sensitive document data.
        if self.approve:
            return True
        answer = input("Review required. Approve extracted document? [y/N] ")
        return answer.strip().lower() in {"y", "yes"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("document", nargs="?", help="document path for real processing")
    args = parser.parse_args()
    if args.demo and args.document:
        parser.error("--demo cannot be combined with a document path")
    if args.demo:
        result = DocumentPipeline(DemoDocumentService(), DemoReviewer()).run(
            b"deterministic demo document"
        )
    elif args.document:
        path = Path(args.document)
        allowed = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff",
                   ".docx", ".xlsx", ".pptx"}
        if not path.is_file():
            parser.error("document does not exist")
        if path.suffix.lower() not in allowed:
            parser.error("unsupported document type")
        if path.stat().st_size > 10_000_000:
            parser.error("document exceeds 10 MB limit")
        with path.open("rb") as stream:
            document = stream.read()
        result = DocumentPipeline(
            NutrientExtractionAdapter(), ConsoleReviewer(approve=False)
        ).run(document)
    else:
        parser.error("use --demo or provide a document path")

    # Keep CLI output safe by exposing metadata and hashes, not extracted values.
    print(json.dumps({
        "status": result.status,
        "document_sha256": result.document_sha256,
        "field_count": len(result.extraction.fields),
        "reviewed": result.reviewed,
        "approved": result.approved,
        "evidence_sha256": result.evidence_sha256,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
