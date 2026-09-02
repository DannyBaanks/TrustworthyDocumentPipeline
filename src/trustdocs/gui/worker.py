"""Background worker for running the pipeline without blocking the UI."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from ..evidence import EvidenceNode, EvidenceRecord, read_record, write_record
from ..ledger import Ledger, verify_ledger
from ..local_adapter import LocalHeuristicAdapter
from ..pipeline import Document, DocumentPipeline, Extraction, PipelineResult
from ..validation import (
    FieldConfidencePolicy,
    LineItemsConsistentRule,
    NonNegativeNumberRule,
    RequiredFieldsRule,
)


@dataclass
class ProcessOutcome:
    result: PipelineResult | None = None
    evidence_path: str | None = None
    error: str | None = None
    trace: list[str] | None = None


class PipelineWorker(QObject):
    """Runs the pipeline in a background thread."""

    started = Signal()
    finished = Signal(object)  # ProcessOutcome
    log_message = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._document_path: Path | None = None
        self._extractor: str = "local"
        self._decision: str | None = None
        self._ledger_path: Path | None = None

    def set_params(
        self,
        document_path: Path,
        extractor: str = "local",
        decision: str | None = None,
        ledger_path: Path | None = None,
    ):
        self._document_path = document_path
        self._extractor = extractor
        self._decision = decision
        self._ledger_path = ledger_path

    def run(self):
        """Called from the worker thread."""
        self.started.emit()
        trace = []
        try:
            trace.append("Loading document...")
            self.log_message.emit(trace[-1])

            path = self._document_path
            if not path or not path.is_file():
                raise FileNotFoundError(f"Document not found: {path}")

            media_type = _media_type(path.suffix.lower())
            with open(path, "rb") as f:
                content = f.read()

            if len(content) > 10_000_000:
                raise ValueError("Document exceeds 10 MB limit")

            document = Document(content, path.name, media_type)
            doc_hash = hashlib.sha256(content).hexdigest()
            trace.append(f"Document hash: sha256:{doc_hash[:16]}...")
            self.log_message.emit(trace[-1])

            trace.append(f"Extractor: {self._extractor}")
            self.log_message.emit(trace[-1])

            if self._extractor == "local":
                service = LocalHeuristicAdapter()
            else:
                from ..nutrient_adapter import NutrientExtractionAdapter
                service = NutrientExtractionAdapter()

            reviewer = _AutoReviewer(self._decision)

            rules = (
                RequiredFieldsRule(("invoice_number", "total_amount")),
                NonNegativeNumberRule("total_amount", "non-negative-total"),
                LineItemsConsistentRule("line_items", "total_amount", "line-items-reconcile"),
                FieldConfidencePolicy(("invoice_number", "total_amount"), 0.85),
            )

            trace.append("Running pipeline...")
            self.log_message.emit(trace[-1])

            pipeline = DocumentPipeline(service, reviewer, rules=rules)
            result = pipeline.run(document)

            trace.append(f"Status: {result.status}")
            trace.append(f"Fields: {len(result.extraction.fields)} extracted")
            trace.append(f"Reviewed: {'yes' if result.reviewed else 'no'}")
            for v in result.validation:
                trace.append(f"  {v.status}: {v.rule_id} — {v.message}")
            self.log_message.emit(trace[-1])

            evidence_path = path.with_suffix(path.suffix + ".evidence.json")
            write_record(evidence_path, result.evidence)
            trace.append(f"Evidence saved: {evidence_path.name}")
            self.log_message.emit(trace[-1])

            if self._ledger_path:
                ledger = Ledger(self._ledger_path)
                ledger.append(
                    execution_id=result.evidence.execution_id,
                    record_sha256=result.evidence.record_sha256,
                    document_sha256=result.document_sha256,
                    decision=result.status,
                )
                trace.append(f"Ledger updated: {self._ledger_path.name}")
                self.log_message.emit(trace[-1])

            outcome = ProcessOutcome(
                result=result,
                evidence_path=str(evidence_path),
                trace=trace,
            )
            self.finished.emit(outcome)

        except Exception as exc:
            trace.append(f"ERROR: {exc}")
            self.log_message.emit(trace[-1])
            outcome = ProcessOutcome(
                error=str(exc),
                trace=trace,
            )
            self.finished.emit(outcome)


class _AutoReviewer:
    """Reviewer that auto-approves unless a specific decision is forced."""

    def __init__(self, forced_decision: str | None = None):
        self._forced = forced_decision

    def review(self, extraction: Extraction) -> bool:
        if self._forced == "reject":
            return False
        if self._forced == "approve":
            return True
        return (extraction.document_confidence or 0) >= 0.5


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
    }.get(suffix, "application/octet-stream")


class VerifyWorker(QObject):
    """Runs evidence verification in a background thread."""

    finished = Signal(bool, list)  # (valid, errors)
    log_message = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._evidence_path: Path | None = None

    def set_params(self, evidence_path: Path):
        self._evidence_path = evidence_path

    def run(self):
        try:
            record = read_record(self._evidence_path)
            valid, errors = record.verify()
            self.log_message.emit(f"Verification: {'VALID' if valid else 'INVALID'}")
            self.finished.emit(valid, errors)
        except Exception as exc:
            self.finished.emit(False, [str(exc)])


class LedgerVerifyWorker(QObject):
    """Runs ledger verification in a background thread."""

    finished = Signal(bool, list, int)  # (valid, errors, entry_count)
    log_message = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ledger_path: Path | None = None
        self._expected_head: str | None = None

    def set_params(self, ledger_path: Path, expected_head: str | None = None):
        self._ledger_path = ledger_path
        self._expected_head = expected_head

    def run(self):
        try:
            valid, errors = verify_ledger(self._ledger_path, expected_head=self._expected_head)
            entries = len(Ledger(self._ledger_path).entries()) if self._ledger_path.exists() else 0
            self.log_message.emit(f"Ledger: {'VALID' if valid else 'INVALID'} ({entries} entries)")
            self.finished.emit(valid, errors, entries)
        except Exception as exc:
            self.finished.emit(False, [str(exc)], 0)


class TamperWorker(QObject):
    """Runs the tamper demo in a background thread, streaming each step."""

    step_line = Signal(str)
    finished = Signal(bool, bool, list)  # (original_valid, tampered_valid, tamper_errors)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._evidence_path: Path | None = None

    def set_params(self, evidence_path: Path):
        self._evidence_path = evidence_path

    @staticmethod
    def build_tampered_copy(record: EvidenceRecord) -> EvidenceRecord:
        body = record.to_dict()
        nodes = body["nodes"]
        if nodes:
            nodes[0]["operation"] = "TAMPERED_" + nodes[0].get("operation", "unknown")
        body["decision"] = "TAMPERED"
        tampered_nodes = tuple(EvidenceNode(**node) for node in nodes)
        return EvidenceRecord(
            body["execution_id"], tampered_nodes, body["decision"], body["record_sha256"]
        )

    def run(self):
        try:
            record = read_record(self._evidence_path)

            self.step_line.emit("=" * 50)
            self.step_line.emit("  TAMPER DEMO")
            self.step_line.emit("=" * 50)
            self.step_line.emit("")
            self.step_line.emit("Step 1: Verify original evidence")
            original_valid, _ = record.verify()
            self.step_line.emit(f"  Result: {'VALID' if original_valid else 'INVALID'}")
            self.step_line.emit("")

            self.step_line.emit("Step 2: Create tampered copy (flip operation + decision)")
            tampered = self.build_tampered_copy(record)
            self.step_line.emit("")

            self.step_line.emit("Step 3: Verify tampered evidence")
            tampered_valid, tamper_errors = tampered.verify()
            self.step_line.emit(f"  Result: {'VALID' if tampered_valid else 'INVALID'}")
            for err in tamper_errors:
                self.step_line.emit(f"  x {err}")
            self.step_line.emit("")

            self.step_line.emit("=" * 50)
            self.step_line.emit("  SUMMARY")
            self.step_line.emit(f"  Original:  {'VALID' if original_valid else 'INVALID'}")
            self.step_line.emit(f"  Tampered:  {'VALID' if tampered_valid else 'INVALID'}")
            if original_valid and not tampered_valid:
                self.step_line.emit("  OK tamper-evident: alteration is detected.")
            elif not original_valid:
                self.step_line.emit("  WARNING original evidence already fails verification.")
            else:
                self.step_line.emit("  UNEXPECTED: tampered copy passed verification.")
            self.finished.emit(original_valid, tampered_valid, tamper_errors)
        except Exception as exc:
            self.step_line.emit(f"ERROR: {exc}")
            self.finished.emit(False, False, [str(exc)])
