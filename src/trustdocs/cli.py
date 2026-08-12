"""Local deterministic demo for the document pipeline."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .pipeline import Document, DocumentPipeline, Extraction, FieldValue
from .nutrient_adapter import NutrientExtractionAdapter
from .evidence import read_record, write_record
from .validation import ConfidenceWarningRule, NonNegativeNumberRule, RequiredFieldsRule


class DemoDocumentService:
    name = "demo-document-service"

    def extract(self, document: Document) -> Extraction:
        return Extraction(
            fields={
                "document_type": FieldValue("demo", 0.99, {"source": "demo"}),
                "bytes": FieldValue(len(document.content), 1.0, {"source": "demo"}),
            },
            document_confidence=0.91,
        )


class DemoReviewer:
    def review(self, extraction: Extraction) -> bool:
        return (extraction.document_confidence or 0) >= 0.5


class WarningDemoDocumentService:
    name = "warning-demo-document-service"

    def extract(self, document: Document) -> Extraction:
        return Extraction(
            fields={
                "invoice_number": FieldValue("DEMO-001", 0.99, {"source": "demo"}),
                "total_amount": FieldValue(125.0, 0.72, {"source": "demo"}),
            },
            document_confidence=0.92,
        )


class ConsoleReviewer:
    def __init__(self, decision: str | None) -> None:
        self.decision = decision

    def review(self, extraction: Extraction) -> bool:
        # Do not print extracted values: they may contain sensitive document data.
        if self.decision == "approve":
            return True
        if self.decision == "reject":
            return False
        answer = input("Review required. Choose [A]pprove/[R]eject (default R): ")
        return answer.strip().lower() in {"a", "approve", "y", "yes"}


def _media_type(suffix: str) -> str:
    return {
        ".pdf": "application/pdf",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".tif": "image/tiff",
        ".tiff": "image/tiff",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    }[suffix]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--demo-warning", action="store_true")
    parser.add_argument("--decision", choices=("approve", "reject"),
                        help="non-interactive human review decision")
    parser.add_argument("first", nargs="?", help="process document or verify command")
    parser.add_argument("second", nargs="?", help="document/evidence path")
    parser.add_argument("--evidence", type=Path)
    args = parser.parse_args()
    if args.demo and args.demo_warning:
        parser.error("--demo and --demo-warning are mutually exclusive")
    if (args.demo or args.demo_warning) and (args.first or args.second):
        parser.error("--demo cannot be combined with a document path")
    if args.demo:
        result = DocumentPipeline(DemoDocumentService(), DemoReviewer()).run(
            Document(b"deterministic demo document", "demo.pdf", "application/pdf")
        )
    elif args.demo_warning:
        result = DocumentPipeline(
            WarningDemoDocumentService(), DemoReviewer(),
            rules=(ConfidenceWarningRule("total_amount", 0.85, "review-low-total-confidence"),),
        ).run(Document(b"deterministic warning document", "warning-demo.pdf", "application/pdf"))
    elif args.first == "verify":
        if not args.second:
            parser.error("verify requires an evidence path")
        try:
            valid, errors = read_record(Path(args.second)).verify()
        except (OSError, ValueError, KeyError) as exc:
            print(json.dumps({"status": "INVALID", "errors": [str(exc)]}, indent=2))
            return 1
        print(json.dumps({"status": "VALID" if valid else "INVALID", "errors": errors}, indent=2))
        return 0 if valid else 1
    elif args.first == "process" and args.second:
        path = Path(args.second)
        allowed = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff",
                   ".docx", ".xlsx", ".pptx"}
        if not path.is_file():
            parser.error("document does not exist")
        if path.suffix.lower() not in allowed:
            parser.error("unsupported document type")
        if path.stat().st_size > 10_000_000:
            parser.error("document exceeds 10 MB limit")
        with path.open("rb") as stream:
            document = Document(
                stream.read(), path.name, _media_type(path.suffix.lower())
            )
        result = DocumentPipeline(
            NutrientExtractionAdapter(), ConsoleReviewer(args.decision),
            rules=(
                RequiredFieldsRule(("invoice_number", "total_amount")),
                NonNegativeNumberRule("total_amount", "non-negative-total"),
            ),
        ).run(document)
    elif args.first:
        path = Path(args.first)
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
            NutrientExtractionAdapter(), ConsoleReviewer(args.decision),
            rules=(
                RequiredFieldsRule(("invoice_number", "total_amount")),
                NonNegativeNumberRule("total_amount", "non-negative-total"),
            ),
        ).run(document)
    else:
        parser.error("use --demo or provide a document path")

    # Keep CLI output safe by exposing metadata and hashes, not extracted values.
    if not args.demo and not args.demo_warning and result.evidence:
        evidence_path = args.evidence or path.with_suffix(path.suffix + ".evidence.json")
        write_record(evidence_path, result.evidence)
    print(json.dumps({
        "status": result.status,
        "document_sha256": result.document_sha256,
        "field_count": len(result.extraction.fields),
        "reviewed": result.reviewed,
        "approved": result.approved,
        "decision": result.decision.status,
        "validation": [finding.status for finding in result.validation],
        "evidence_sha256": result.evidence_sha256,
        "execution_id": result.evidence.execution_id,
        "evidence_path": (
            str(evidence_path) if not args.demo and not args.demo_warning else None
        ),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
