"""Local deterministic demo for the document pipeline."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .attack_demo import run_attack_demo
from .evidence import read_record, write_record
from .nutrient_adapter import NutrientExtractionAdapter
from .pipeline import Document, DocumentPipeline, Extraction, FieldValue
from .provider_swap import run_provider_swap
from .render import render_pretty
from .validation import (
    ConfidenceWarningRule,
    LineItemsConsistentRule,
    NonNegativeNumberRule,
    RequiredFieldsRule,
)


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
    parser.add_argument("third", nargs="?", help="ledger trace argument")
    parser.add_argument("--extractor", choices=("nutrient", "local"), default="nutrient",
                        help="which extraction service to use (local needs no key)")
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--ledger", type=Path,
                        help="append the decision to this ledger, or the ledger to query")
    parser.add_argument("--expect-head", dest="expect_head",
                        help="anchor published elsewhere; catches a truncated tail")
    parser.add_argument("--json", action="store_true",
                        help="print raw JSON instead of the formatted summary")
    return parser


def _run_ledger_command(args, parser) -> dict[str, object]:
    """`ledger verify|head|summary|trace <sha>`.

    Kept in one place because every branch returns the same result shape the
    renderer expects, and because a missing ledger has to fail as a reported
    outcome rather than a traceback.
    """
    from .ledger import Ledger, verify_ledger

    action = args.second
    if action not in {"verify", "head", "summary", "trace", "console"}:
        parser.error("ledger requires one of: verify, head, summary, trace, console")
    if not args.ledger:
        parser.error("ledger commands require --ledger PATH")

    base = {"kind": "ledger", "_json_requested": args.json, "action": action,
            "ledger_path": str(args.ledger)}

    if action == "verify":
        valid, errors = verify_ledger(args.ledger, expected_head=args.expect_head)
        entries = len(Ledger(args.ledger).entries()) if args.ledger.exists() else 0
        return {**base, "status": "VALID" if valid else "INVALID",
                "entries": entries, "errors": errors}

    if action == "head":
        return {**base, "status": "OK", "head": Ledger(args.ledger).head(), "errors": []}

    if action == "summary":
        return {**base, "status": "OK", "summary": Ledger(args.ledger).summary(),
                "errors": []}

    if action == "console":
        from .console import write_console
        out = args.evidence or Path("console.html")
        write_console(args.ledger, out, expected_head=args.expect_head)
        return {**base, "status": "OK", "console_path": str(out),
                "entries": len(Ledger(args.ledger).entries()), "errors": []}

    # trace
    if not args.third:
        parser.error("ledger trace requires a document sha256")
    found = Ledger(args.ledger).find_document(args.third)
    return {**base, "status": "OK", "found": found is not None,
            "entry": found.to_dict() if found else None, "errors": []}


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

    if args.first == "attack":
        run_attack_demo()
        return {"kind": "attack", "_json_requested": False, "status": "OK"}

    if args.first == "swap":
        run_provider_swap()
        return {"kind": "swap", "_json_requested": False, "status": "OK"}

    if args.first == "ledger":
        return _run_ledger_command(args, parser)

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

    # The ledger is what makes a set of decisions auditable rather than a pile
    # of independently-valid files. Demos append too, so the chain can be shown
    # end to end without an API key.
    ledger_entry = None
    if args.ledger:
        from .ledger import Ledger
        ledger_entry = Ledger(args.ledger).append(
            execution_id=result.evidence.execution_id,
            record_sha256=result.evidence.record_sha256,
            document_sha256=result.document_sha256,
            decision=result.status,
        ).to_dict()

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
        "ledger_entry": ledger_entry,
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
    if args.extractor == "local":
        from .local_adapter import LocalHeuristicAdapter
        service = LocalHeuristicAdapter()
    else:
        service = NutrientExtractionAdapter()

    return DocumentPipeline(
        service, ConsoleReviewer(args.decision),
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


def _render_ledger_pretty(outcome: dict) -> str:
    """Render a ledger outcome.

    Kept separate from the process renderer because they share no fields; the
    first version routed ledger output through render_pretty and crashed on a
    missing document hash.
    """
    from .render import DIM, GREEN, RED, RESET, supports_color
    color = supports_color()
    green, red, dim, reset = (GREEN, RED, DIM, RESET) if color else ("", "", "", "")
    ok = outcome["status"] in {"VALID", "OK"}
    tint = green if ok else red
    icon = ("✓" if ok else "✗") if color else ("+" if ok else "!")

    lines = [f"{tint}{icon} ledger {outcome['action']}: {outcome['status']}{reset}",
             f"  {dim}{outcome['ledger_path']}{reset}"]

    if outcome["action"] == "verify":
        lines.append(f"  Entries:      {outcome['entries']}")
    elif outcome["action"] == "head":
        head = outcome["head"]
        lines.append(f"  Head:         {head if head else '(empty ledger)'}")
        if head:
            lines.append(f"  {dim}Publish this value where the writer cannot reach it.{reset}")
    elif outcome["action"] == "summary":
        summary = outcome["summary"]
        lines.append(f"  Decisions:    {summary['total']}")
        for name, count in sorted(summary["by_decision"].items()):
            lines.append(f"    {count:>4}  {name}")
        if summary["first_recorded_at"]:
            lines.append(f"  {dim}From {summary['first_recorded_at']}{reset}")
            lines.append(f"  {dim}To   {summary['last_recorded_at']}{reset}")
    elif outcome["action"] == "console":
        lines.append(f"  Entries:      {outcome['entries']}")
        lines.append(f"  Written to:   {outcome['console_path']}")
        lines.append(f"  {dim}Open it in a browser; it recomputes every hash itself.{reset}")
    elif outcome["action"] == "trace":
        if outcome["found"]:
            entry = outcome["entry"]
            lines.append(f"  Decision:     {entry['decision']}")
            lines.append(f"  Recorded:     {entry['recorded_at']}")
            lines.append(f"  Entry:        #{entry['sequence']}")
        else:
            lines.append("  No decision recorded for that document.")

    for error in outcome.get("errors") or []:
        lines.append(f"  {'✗' if color else '-'} {error}")
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
    elif outcome["kind"] == "attack":
        pass  # attack demo prints its own output
    elif outcome["kind"] == "swap":
        pass  # provider swap demo prints its own output
    elif outcome["kind"] == "verify":
        print(_render_verify_pretty(outcome))
    elif outcome["kind"] == "ledger":
        print(_render_ledger_pretty(outcome))
    else:
        print(render_pretty(outcome))

    if outcome["kind"] in {"verify", "ledger"}:
        return 0 if outcome["status"] in {"VALID", "OK"} else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
