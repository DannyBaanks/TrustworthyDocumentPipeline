"""Local deterministic demo for the document pipeline."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .pipeline import Document, DocumentPipeline, Extraction, FieldValue
from .nutrient_adapter import NutrientExtractionAdapter
from .evidence import read_record, write_record
from .render import render_pretty
from .validation import ConfidenceWarningRule, LineItemsConsistentRule, NonNegativeNumberRule, RequiredFieldsRule


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


class InconsistentDemoDocumentService:
    name = "inconsistent-demo-document-service"

    def extract(self, document: Document) -> Extraction:
        return Extraction(
            fields={
                "invoice_number": FieldValue("DEMO-002", 0.99, {"source": "demo"}),
                "total_amount": FieldValue(118.0, 0.98, {"source": "demo"}),
                "line_items": FieldValue([
                    {"description": "Widget A", "quantity": 2, "unit_price": 10.0, "total": 20.0},
                    {"description": "Widget B", "quantity": 3, "unit_price": 15.0, "total": 45.0},
                ], 0.98, {"source": "demo"}),
            },
            document_confidence=0.95,
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--demo-warning", action="store_true")
    parser.add_argument("--demo-inconsistent", action="store_true")
    parser.add_argument("--decision", choices=("approve", "reject"),
                        help="non-interactive human review decision")
    parser.add_argument("first", nargs="?", help="process document or verify command")
    parser.add_argument("second", nargs="?", help="document/evidence path")
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--json", action="store_true",
                        help="print raw JSON instead of the formatted summary")
    return parser


def run(argv: list[str] | None = None) -> dict[str, object]:
    """Parse args, run the pipeline or verify command, and return a
    structured outcome. main() renders it (pretty by default, --json for
    scripting); both read from this single result shape."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if sum(bool(flag) for flag in (args.demo, args.demo_warning, args.demo_inconsistent)) > 1:
        parser.error("--demo, --demo-warning and --demo-inconsistent are mutually exclusive")
    if (args.demo or args.demo_warning or args.demo_inconsistent) and (args.first or args.second):
        parser.error("--demo cannot be combined with a document path")

    if args.first == "verify":
        if not args.second:
            parser.error("verify requires an evidence path")
        try:
            record = read_record(Path(args.second))
            valid, errors = record.verify()
        except (OSError, ValueError, KeyError) as exc:
            return {"kind": "verify", "_json_requested": args.json, "status": "INVALID",
                    "decision": None, "errors": [str(exc)]}
        return {
            "kind": "verify",
            "_json_requested": args.json,
            "status": "VALID" if valid else "INVALID",
            "decision": record.decision,
            "errors": errors,
        }

    is_demo = any((args.demo, args.demo_warning, args.demo_inconsistent))
    path: Path | None = None

    if args.demo:
        result = DocumentPipeline(DemoDocumentService(), DemoReviewer()).run(
            Document(b"deterministic demo document", "demo.pdf", "application/pdf")
        )
    elif args.demo_warning:
        result = DocumentPipeline(
            WarningDemoDocumentService(), DemoReviewer(),
            rules=(ConfidenceWarningRule("total_amount", 0.85, "review-low-total-confidence"),),
        ).run(Document(b"deterministic warning document", "warning-demo.pdf", "application/pdf"))
    elif args.demo_inconsistent:
        result = DocumentPipeline(
            InconsistentDemoDocumentService(), DemoReviewer(),
            rules=(LineItemsConsistentRule("line_items", "total_amount", "line-items-reconcile"),),
        ).run(Document(b"deterministic inconsistent document", "inconsistent-demo.pdf", "application/pdf"))
    elif args.first == "process" and args.second:
        path = Path(args.second)
        result = _run_real_document(path, args, parser)
    elif args.first:
        path = Path(args.first)
        result = _run_real_document(path, args, parser)
    else:
        parser.error("use --demo or provide a document path")

    evidence_path: Path | None = None
    if not is_demo and result.evidence:
        evidence_path = args.evidence or path.with_suffix(path.suffix + ".evidence.json")
        write_record(evidence_path, result.evidence)

    return {
        "kind": "process",
        "_json_requested": args.json,
        "status": result.status,
        "document_sha256": result.document_sha256,
        "field_count": len(result.extraction.fields),
        "reviewed": result.reviewed,
        "approved": result.approved,
        "decision": result.decision.status,
        "validation": [
            {"rule_id": f.rule_id, "status": f.status, "message": f.message}
            for f in result.validation
        ],
        "evidence_sha256": result.evidence_sha256,
        "execution_id": result.evidence.execution_id,
        "evidence_path": str(evidence_path) if evidence_path else None,
    }


def _run_real_document(path: Path, args: argparse.Namespace,
                        parser: argparse.ArgumentParser):
    allowed = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff",
               ".docx", ".xlsx", ".pptx"}
    if not path.is_file():
        parser.error("document does not exist")
    if path.suffix.lower() not in allowed:
        parser.error("unsupported document type")
    if path.stat().st_size > 10_000_000:
        parser.error("document exceeds 10 MB limit")
    with path.open("rb") as stream:
        document = Document(stream.read(), path.name, _media_type(path.suffix.lower()))
    return DocumentPipeline(
        NutrientExtractionAdapter(), ConsoleReviewer(args.decision),
        rules=(
            RequiredFieldsRule(("invoice_number", "total_amount")),
            NonNegativeNumberRule("total_amount", "non-negative-total"),
        ),
    ).run(document)


def _render_verify_pretty(outcome: dict) -> str:
    from .render import GREEN, RED, RESET, supports_color
    color_enabled = supports_color()
    ok = outcome["status"] == "VALID"
    color = (GREEN if ok else RED) if color_enabled else ""
    reset = RESET if color_enabled else ""
    icon = "✓" if ok else "✗"
    lines = [f"{color}{icon} {outcome['status']}{reset}"]
    if outcome.get("decision"):
        lines.append(f"  Recorded decision: {outcome['decision']}")
    for error in outcome.get("errors") or []:
        lines.append(f"  {'✗' if color_enabled else '-'} {error}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    # Windows consoles/redirected output don't always default to UTF-8;
    # without this, the checkmarks below raise UnicodeEncodeError.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    outcome = run(argv)
    json_requested = outcome.pop("_json_requested", False)

    if json_requested:
        printable = {k: v for k, v in outcome.items() if k != "kind"}
        print(json.dumps(printable, indent=2))
    elif outcome["kind"] == "verify":
        print(_render_verify_pretty(outcome))
    else:
        print(render_pretty(outcome))

    if outcome["kind"] == "verify":
        return 0 if outcome["status"] == "VALID" else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
