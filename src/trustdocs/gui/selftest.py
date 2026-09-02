"""In-app diagnostics: one check per button behaviour.

Each check drives the exact code path its button triggers, against a hidden,
disposable MainWindow and a temporary directory, so the user's live session is
never modified. A check that throws is reported as FAIL with the exception.
"""
from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from ..evidence import read_record
from .main_window import MainWindow
from .worker import (
    LedgerVerifyWorker,
    PipelineWorker,
    ProcessOutcome,
    TamperWorker,
    VerifyWorker,
)

DEMO_TEXT = b"Invoice Number: INV-SELFTEST-001  Total Due: $42.50  Currency: USD"


def minimal_pdf() -> bytes:
    """A tiny but structurally valid single-page PDF for offline audits."""
    header = b"%PDF-1.4\n"
    stream_text = b"BT /F1 12 Tf 72 720 Td (" + DEMO_TEXT + b") Tj ET\n"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream_text)).encode() + b" >>\nstream\n"
        + stream_text + b"endstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    body = bytearray()
    offsets = []
    position = len(header)
    for number, content in enumerate(objects, start=1):
        entry = f"{number} 0 obj\n".encode() + content + b"\nendobj\n"
        offsets.append(position)
        body += entry
        position += len(entry)

    xref_position = position
    xref = f"xref\n0 {len(objects) + 1}\n".encode()
    xref += b"0000000000 65535 f \n"
    for offset in offsets:
        xref += f"{offset:010d} 00000 n \n".encode()
    trailer = (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_position}\n%%EOF\n"
    ).encode()

    return header + bytes(body) + xref + trailer


DEMO_BYTES = minimal_pdf()


@dataclass(frozen=True)
class Check:
    id: str
    title: str
    fn: object


@dataclass(frozen=True)
class CheckResult:
    id: str
    title: str
    ok: bool
    detail: str


class SelfTestSession:
    def __init__(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="trustdocs-selftest-")
        self.root = Path(self._tmp.name)
        self.probe = MainWindow()
        self.outcome: ProcessOutcome | None = None

    def close(self):
        self.probe.close()
        try:
            self._tmp.cleanup()
        except OSError:
            pass

    def _subdir(self, name: str) -> Path:
        path = self.root / name
        path.mkdir(parents=True, exist_ok=True)
        return path

    def checks(self) -> list[Check]:
        return [
            Check("T01", "initial state machine", self._check_initial_state),
            Check("T02", "failed process keeps actions disabled", self._check_process_failure),
            Check("T03", "select enables Process and resets stale state", self._check_select),
            Check("T04", "Process button path: pipeline end-to-end", self._check_pipeline_e2e),
            Check("T05", "results populate all tabs and enable actions", self._check_tabs_populated),
            Check("T06", "Verify Evidence reports VALID", self._check_verify_worker),
            Check("T07", "Tamper demo detects alteration", self._check_tamper_detection),
            Check("T08", "Verify Ledger validates chained entries", self._check_ledger_worker),
            Check("T09", "Export writes a complete identical record", self._check_export),
            Check("T10", "corrupted evidence is rejected", self._check_corruption_detected),
        ]

    def _check_initial_state(self) -> CheckResult:
        p = self.probe
        buttons = {
            "Process": p._process_btn,
            "Verify Evidence": p._verify_btn,
            "Verify Ledger": p._ledger_verify_btn,
            "Export": p._export_btn,
            "Run Tamper Demo": p._tamper_btn,
        }
        enabled = [name for name, btn in buttons.items() if btn.isEnabled()]
        if enabled:
            return CheckResult("T01", "initial state machine", False,
                               f"enabled before any action: {', '.join(enabled)}")
        if "Ready" not in p._status_label.text():
            return CheckResult("T01", "initial state machine", False,
                               f"status shows {p._status_label.text()!r}")
        return CheckResult("T01", "initial state machine", True,
                           f"{p._tabs.count()} tabs, every action disabled")

    def _check_process_failure(self) -> CheckResult:
        p = self.probe
        p._on_process_done(ProcessOutcome(result=None, error="simulated failure"))
        if p._export_btn.isEnabled():
            return CheckResult("T02", "failed process keeps actions disabled", False,
                               "Export became clickable after a failed run")
        if "Error" not in p._status_label.text():
            return CheckResult("T02", "failed process keeps actions disabled", False,
                               f"status shows {p._status_label.text()!r}")
        return CheckResult("T02", "failed process keeps actions disabled", True,
                           "error surfaced, no action button unlocked")

    def _check_select(self) -> CheckResult:
        p = self.probe
        doc = self._subdir("select") / "demo.pdf"
        doc.write_bytes(DEMO_BYTES)

        p._last_result = object()
        p._export_btn.setEnabled(True)

        p._apply_selected_document(doc)

        problems = []
        if not p._process_btn.isEnabled():
            problems.append("Process stayed disabled")
        if p._last_result is not None:
            problems.append("stale result survived")
        if p._export_btn.isEnabled():
            problems.append("Export stayed enabled without evidence")
        if p._doc_label.text() != "demo.pdf":
            problems.append(f"label shows {p._doc_label.text()!r}")
        if problems:
            return CheckResult("T03", "select enables Process and resets stale state",
                               False, "; ".join(problems))
        return CheckResult("T03", "select enables Process and resets stale state",
                           True, "fresh document, stale actions cleared")

    def _check_pipeline_e2e(self) -> CheckResult:
        workdir = self._subdir("e2e")
        doc = workdir / "invoice.pdf"
        doc.write_bytes(DEMO_BYTES)
        ledger_path = workdir / "ledger.jsonl"

        worker = PipelineWorker()
        outcomes: list[ProcessOutcome] = []
        worker.finished.connect(outcomes.append)
        worker.set_params(doc, extractor="local", decision="approve",
                          ledger_path=ledger_path)
        worker.run()

        if len(outcomes) != 1:
            return CheckResult("T04", "Process button path: pipeline end-to-end", False,
                               f"expected 1 outcome, got {len(outcomes)}")
        outcome = outcomes[0]
        if outcome.error:
            return CheckResult("T04", "Process button path: pipeline end-to-end", False,
                               outcome.error)
        if outcome.result.status != "APPROVED_BY_HUMAN":
            return CheckResult("T04", "Process button path: pipeline end-to-end", False,
                               f"status={outcome.result.status}")
        rule_ids = {f.rule_id for f in outcome.result.validation}
        if "field-confidence-gate" not in rule_ids:
            return CheckResult("T04", "Process button path: pipeline end-to-end", False,
                               "field-confidence-gate rule did not fire")
        if outcome.result.decision.review is None:
            return CheckResult("T04", "Process button path: pipeline end-to-end", False,
                               "no ReviewRecord was produced for the human review")
        evidence_path = Path(outcome.evidence_path)
        if not evidence_path.exists():
            return CheckResult("T04", "Process button path: pipeline end-to-end", False,
                               "evidence file was not written")
        if not ledger_path.exists():
            return CheckResult("T04", "Process button path: pipeline end-to-end", False,
                               "ledger file was not written")
        self.outcome = outcome
        self.evidence_path = evidence_path
        self.ledger_path = ledger_path
        return CheckResult("T04", "Process button path: pipeline end-to-end", True,
                           f"{outcome.result.status}, evidence+ledger written")

    def _check_tabs_populated(self) -> CheckResult:
        p = self.probe
        if self.outcome is None:
            return CheckResult("T05", "results populate all tabs and enable actions",
                               False, "no outcome available")
        p._apply_selected_document(self.evidence_path.parent / "invoice.pdf")
        p._on_process_done(self.outcome)

        problems = []
        if "fields" not in p._extraction_view.toPlainText():
            problems.append("extraction empty")
        if not p._validation_view.toPlainText().strip():
            problems.append("validation empty")
        if "APPROVED_BY_HUMAN" not in p._decision_view.toPlainText():
            problems.append("decision missing status")
        if "review" not in p._decision_view.toPlainText():
            problems.append("decision missing review record")
        if "record_sha256" not in p._evidence_view.toPlainText():
            problems.append("evidence view empty")
        for name, btn in (("Export", p._export_btn), ("Verify", p._verify_btn),
                          ("Tamper", p._tamper_btn), ("Ledger", p._ledger_verify_btn)):
            if not btn.isEnabled():
                problems.append(f"{name} stayed disabled")
        if problems:
            return CheckResult("T05", "results populate all tabs and enable actions",
                               False, "; ".join(problems))
        return CheckResult("T05", "results populate all tabs and enable actions",
                           True, "4 tabs filled, 4 actions unlocked")

    def _check_verify_worker(self) -> CheckResult:
        worker = VerifyWorker()
        results: list[tuple[bool, list]] = []
        worker.finished.connect(lambda v, e: results.append((v, e)))
        worker.set_params(self.evidence_path)
        worker.run()
        valid, errors = results[0] if results else (False, ["no signal"])
        if not valid:
            return CheckResult("T06", "Verify Evidence reports VALID", False,
                               "; ".join(errors))
        return CheckResult("T06", "Verify Evidence reports VALID", True,
                           "hash chain intact")

    def _check_tamper_detection(self) -> CheckResult:
        record = read_record(self.evidence_path)
        tampered = TamperWorker.build_tampered_copy(record)
        valid, errors = tampered.verify()
        if valid:
            return CheckResult("T07", "Tamper demo detects alteration", False,
                               "tampered copy verified as VALID")
        return CheckResult("T07", "Tamper demo detects alteration", True,
                           f"{len(errors)} integrity error(s) raised")

    def _check_ledger_worker(self) -> CheckResult:
        worker = LedgerVerifyWorker()
        results: list[tuple[bool, list, int]] = []
        worker.finished.connect(lambda v, e, n: results.append((v, e, n)))
        worker.set_params(self.ledger_path)
        worker.run()
        valid, errors, count = results[0] if results else (False, ["no signal"], 0)
        if not valid or count < 1:
            return CheckResult("T08", "Verify Ledger validates chained entries", False,
                               "; ".join(errors) or f"{count} entries")
        return CheckResult("T08", "Verify Ledger validates chained entries", True,
                           f"chain intact ({count} entry)")

    def _check_export(self) -> CheckResult:
        p = self.probe
        target = self._subdir("export") / "copy.json"
        written = p._export_to(target)
        record = read_record(written)
        original = read_record(self.evidence_path)
        if record.record_sha256 != original.record_sha256:
            return CheckResult("T09", "Export writes a complete identical record", False,
                               "hash differs from source evidence")

        suffixless = self._subdir("export") / "noext"
        written2 = p._export_to(suffixless)
        if written2.suffix != ".json" or not written2.exists():
            return CheckResult("T09", "Export writes a complete identical record", False,
                               "missing .json suffix was not added")
        return CheckResult("T09", "Export writes a complete identical record", True,
                           f"{written.name} byte-equivalent hash")

    def _check_corruption_detected(self) -> CheckResult:
        target = self._subdir("corrupt") / "broken.json"
        text = self.evidence_path.read_text(encoding="utf-8")
        marker = '"record_sha256": "'
        start = text.index(marker) + len(marker)
        flipped = "0" if text[start] != "0" else "1"
        target.write_text(text[:start] + flipped + text[start + 1:], encoding="utf-8")
        valid, errors = read_record(target).verify()
        if valid:
            return CheckResult("T10", "corrupted evidence is rejected", False,
                               "flipped byte passed verification")
        return CheckResult("T10", "corrupted evidence is rejected", True,
                           f"detected: {errors[0]}")


def run_check(session: SelfTestSession, check: Check) -> CheckResult:
    try:
        return check.fn()
    except Exception as exc:
        return CheckResult(check.id, check.title, False, f"{type(exc).__name__}: {exc}")
