"""Button-by-button audit: every control must demonstrably do its job.

Each test drives the real handler the button is wired to (file dialogs are
patched, workers run on real QThreads with the event loop pumping), and then
asserts an observable effect on screen or on disk.
"""
from __future__ import annotations

import os
import shutil
import sys
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication

    _app = QApplication.instance() or QApplication(sys.argv)
    HAS_PYSIDE6 = True
except ImportError:
    HAS_PYSIDE6 = False

_skip_reason = "PySide6 no instalado — saltando tests de GUI"

SAMPLE = Path(__file__).parent.parent / "sample" / "invoice.pdf"


def _demo_bytes() -> bytes:
    from trustdocs.gui.selftest import minimal_pdf

    return minimal_pdf()


def _pump_until(predicate, timeout: float = 15.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        _app.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    return False


@unittest.skipUnless(HAS_PYSIDE6, _skip_reason)
class ButtonAuditTests(unittest.TestCase):
    """One test per visible button."""

    def setUp(self):
        from trustdocs.gui.main_window import MainWindow

        self.window = MainWindow()
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.addCleanup(self.window.close)

    def _write_doc(self, name="invoice.pdf") -> Path:
        path = Path(self._tmp.name) / name
        if name == "invoice.pdf" and SAMPLE.exists():
            shutil.copyfile(SAMPLE, path)
            return path
        path.write_bytes(_demo_bytes())
        return path

    def _process_async(self, doc: Path):
        from trustdocs.gui.worker import PipelineWorker

        worker = PipelineWorker()
        outcomes = []
        worker.finished.connect(outcomes.append)
        worker.set_params(doc, extractor="local", decision="approve",
                          ledger_path=doc.parent / "ledger.jsonl")
        thread_results = []
        worker.finished.connect(lambda _: thread_results.append(1))
        worker.run()
        return outcomes[0]

    # ── Select PDF ────────────────────────────────────────────────────────
    def test_select_pdf_button_opens_dialog_and_enables_process(self):
        from PySide6.QtWidgets import QFileDialog

        doc = self._write_doc()
        original = QFileDialog.getOpenFileName
        QFileDialog.getOpenFileName = staticmethod(lambda *a, **k: (str(doc), ""))
        try:
            self.window._select_btn.click()
            _app.processEvents()
        finally:
            QFileDialog.getOpenFileName = staticmethod(original)

        self.assertTrue(self.window._process_btn.isEnabled(),
                        "Process stayed disabled after a successful selection")
        self.assertEqual(self.window._doc_label.text(), doc.name)

    def test_select_resets_stale_state_from_previous_document(self):
        doc = self._write_doc("second.pdf")
        self.window._last_result = object()
        self.window._export_btn.setEnabled(True)

        self.window._apply_selected_document(doc)

        self.assertIsNone(self.window._last_result,
                          "result of previous document survived selection")
        self.assertFalse(self.window._export_btn.isEnabled())

    # ── Process ───────────────────────────────────────────────────────────
    def test_process_button_runs_pipeline_and_unlocks_actions(self):
        doc = self._write_doc()
        self.window._apply_selected_document(doc)

        self.window._process_btn.click()

        self.assertTrue(
            _pump_until(lambda: self.window._export_btn.isEnabled()),
            "Process finished but Export never unlocked",
        )
        self.assertIsNotNone(self.window._last_result)
        self.assertIn("fields", self.window._extraction_view.toPlainText())
        self.assertIn("record_sha256", self.window._evidence_view.toPlainText())
        for btn in (self.window._verify_btn, self.window._tamper_btn,
                    self.window._ledger_verify_btn):
            self.assertTrue(btn.isEnabled(), f"{btn.text()} stayed disabled after Process")
        ledger = doc.parent / "ledger.jsonl"
        self.assertTrue(ledger.exists(), "Process did not append to the ledger")

    def test_process_writes_ledger_entry_next_to_document(self):
        doc = self._write_doc()
        self.window._apply_selected_document(doc)
        self.window._process_btn.click()

        self.assertTrue(_pump_until(lambda: (doc.parent / "ledger.jsonl").exists()),
                        "ledger.jsonl never appeared next to the document")
        from trustdocs.ledger import Ledger, verify_ledger

        ledger_path = doc.parent / "ledger.jsonl"
        valid, errors = verify_ledger(ledger_path)
        self.assertTrue(valid, errors)
        entries = Ledger(ledger_path).entries()
        self.assertEqual(len(entries), 1)

    def test_process_error_is_reported_and_buttons_recover(self):
        missing = Path(self._tmp.name) / "ghost.pdf"
        self.window._apply_selected_document(missing)
        self.window._process_btn.click()

        ok = _pump_until(lambda: "Error" in self.window._status_label.text())
        self.assertTrue(ok, "error status never shown for a missing document")
        self.assertTrue(self.window._process_btn.isEnabled(),
                        "Process stayed locked after failure")

    # ── Verify Evidence ───────────────────────────────────────────────────
    def test_verify_evidence_button_reports_valid(self):
        outcome = self._process_async(self._write_doc())
        self.window._on_process_done(outcome)

        self.window._verify_btn.click()
        ok = _pump_until(lambda: "Evidence verification: VALID" in self.window._log.toPlainText())
        self.assertTrue(ok, "verification result never reached the trace log")
        self.assertIn("VERIFIED", self.window._evidence_view.toPlainText())

    # ── Verify Ledger ─────────────────────────────────────────────────────
    def test_verify_ledger_button_reports_valid_chain(self):
        doc = self._write_doc()
        self.window._apply_selected_document(doc)
        outcome = self._process_async(doc)
        self.window._on_process_done(outcome)

        self.window._ledger_verify_btn.click()
        ok = _pump_until(lambda: "Ledger verification: VALID" in self.window._log.toPlainText())
        self.assertTrue(ok, "ledger verification result never reached the trace log")

    # ── Export ────────────────────────────────────────────────────────────
    def test_export_button_writes_identical_record_to_chosen_file(self):
        from PySide6.QtWidgets import QFileDialog

        outcome = self._process_async(self._write_doc())
        self.window._on_process_done(outcome)

        target = Path(self._tmp.name) / "exported" / "copy.json"
        target.parent.mkdir()
        original = QFileDialog.getSaveFileName
        QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (str(target), ""))
        try:
            self.window._export_btn.click()
            _app.processEvents()
        finally:
            QFileDialog.getSaveFileName = staticmethod(original)

        self.assertTrue(target.exists(), "Export wrote nothing")
        from trustdocs.evidence import read_record

        self.assertEqual(read_record(target).record_sha256,
                         read_record(Path(outcome.evidence_path)).record_sha256,
                         "exported record hash differs from source evidence")
        self.assertIn("Exported to", self.window._status_bar.currentMessage())
        self.assertIn("Evidence exported", self.window._log.toPlainText())

    def test_export_disabled_without_a_result_and_reports_why(self):
        self.window._export_btn.setEnabled(True)
        self.window._export_btn.click()
        _app.processEvents()
        self.assertIn("Nothing to export", self.window._log.toPlainText())

    # ── Run Tamper Demo ───────────────────────────────────────────────────
    def test_tamper_demo_button_shows_detection_verdict(self):
        outcome = self._process_async(self._write_doc())
        self.window._on_process_done(outcome)

        self.window._tamper_btn.click()
        ok = _pump_until(lambda: "SUMMARY" in self.window._tamper_view.toPlainText())
        self.assertTrue(ok, "tamper demo output never appeared")

        text = self.window._tamper_view.toPlainText()
        self.assertIn("Original:  VALID", text)
        self.assertIn("Tampered:  INVALID", text)
        self.assertIn("tamper-evident", text.lower())
        self.assertTrue(self.window._tamper_btn.isEnabled(),
                        "Run Tamper Demo stayed locked after finishing")

    # ── Run Self-Test ─────────────────────────────────────────────────────
    def test_self_test_button_runs_all_checks_and_passes(self):
        self.window._selftest_btn.click()

        ok = _pump_until(
            lambda: "SELF-TEST RESULT" in self.window._selftest_view.toPlainText(),
            timeout=60,
        )
        self.assertTrue(ok, "self-test never produced a summary")

        text = self.window._selftest_view.toPlainText()
        self.assertNotIn("[FAIL]", text, f"failing checks:\n{text}")
        self.assertIn("10/10 passed", text)
        self.assertTrue(self.window._selftest_btn.isEnabled())


@unittest.skipUnless(HAS_PYSIDE6, _skip_reason)
class DiagnosticsParityTests(unittest.TestCase):
    """The in-app self-test must stay green when run directly."""

    def test_session_checks_all_pass(self):
        from trustdocs.gui.selftest import SelfTestSession, run_check

        session = SelfTestSession()
        try:
            failures = [
                result
                for check in session.checks()
                if not (result := run_check(session, check)).ok
            ]
        finally:
            session.close()
        self.assertEqual(failures, [], [f"{r.id} {r.title}: {r.detail}" for r in failures])


if __name__ == "__main__":
    unittest.main()
