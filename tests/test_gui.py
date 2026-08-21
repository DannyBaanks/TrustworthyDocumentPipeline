"""Tests for the GUI module."""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import sys
import os

# Force offscreen rendering for headless testing
os.environ["QT_QPA_PLATFORM"] = "offscreen"

try:
    from PySide6.QtCore import Qt, QTimer, QEventLoop
    from PySide6.QtWidgets import QApplication

    # Create app once for all tests
    _app = QApplication.instance() or QApplication(sys.argv)
    HAS_PYSIDE6 = True
except ImportError:
    HAS_PYSIDE6 = False

_skip_reason = "PySide6 no instalado — saltando tests de GUI"

SAMPLE = Path(__file__).parent.parent / "sample" / "invoice.pdf"


@unittest.skipUnless(HAS_PYSIDE6, _skip_reason)
class GuiSmokeTests(unittest.TestCase):
    """Smoke tests: verify the GUI starts and key widgets exist."""

    def test_main_window_creates(self):
        from trustdocs.gui.main_window import MainWindow

        window = MainWindow()
        self.assertIsNotNone(window)
        self.assertEqual(window.windowTitle(), "Trustworthy Document Pipeline")
        window.close()

    def test_toolbar_widgets_exist(self):
        from trustdocs.gui.main_window import MainWindow

        window = MainWindow()
        self.assertIsNotNone(window._extractor_combo)
        self.assertIsNotNone(window._decision_combo)
        self.assertIsNotNone(window._status_label)
        self.assertEqual(window._extractor_combo.count(), 2)
        self.assertEqual(window._decision_combo.count(), 3)
        window.close()

    def test_tabs_exist(self):
        from trustdocs.gui.main_window import MainWindow

        window = MainWindow()
        self.assertEqual(window._tabs.count(), 5)
        window.close()

    def test_select_button_disabled_initially(self):
        from trustdocs.gui.main_window import MainWindow

        window = MainWindow()
        self.assertFalse(window._process_btn.isEnabled())
        self.assertFalse(window._verify_btn.isEnabled())
        self.assertFalse(window._tamper_btn.isEnabled())
        window.close()

    def test_status_starts_ready(self):
        from trustdocs.gui.main_window import MainWindow

        window = MainWindow()
        self.assertIn("Ready", window._status_label.text())
        window.close()


@unittest.skipUnless(HAS_PYSIDE6, _skip_reason)
class GuiEndToEndTests(unittest.TestCase):
    """Full end-to-end: open GUI -> select doc -> process -> verify -> tamper."""

    def _run_with_timeout(self, func, timeout_ms=10000):
        """Run func() and pump events until the event loop finishes or timeout."""
        loop = QEventLoop()
        result = [None]

        def wrapper():
            result[0] = func()
            loop.quit()

        QTimer.singleShot(0, wrapper)
        QTimer.singleShot(timeout_ms, loop.quit)
        loop.exec()
        return result[0]

    def test_full_pipeline_flow(self):
        """The complete judge flow: select -> process -> see extraction -> verify -> tamper."""
        if not SAMPLE.exists():
            self.skipTest("sample/invoice.pdf not found")

        from trustdocs.gui.main_window import MainWindow

        window = MainWindow()

        # ── 1. Select document ─────────────────────────────────────────────
        window._document_path = SAMPLE
        window._doc_label.setText(SAMPLE.name)
        window._process_btn.setEnabled(True)
        self.assertEqual(window._doc_label.text(), "invoice.pdf")

        # ── 2. Configure extractor ─────────────────────────────────────────
        window._extractor_combo.setCurrentText("local")
        window._decision_combo.setCurrentText("approve")
        self.assertEqual(window._extractor_combo.currentText(), "local")
        self.assertEqual(window._decision_combo.currentText(), "approve")

        # ── 3. Run pipeline synchronously ──────────────────────────────────
        from trustdocs.gui.worker import PipelineWorker

        worker = PipelineWorker()
        worker.set_params(SAMPLE, extractor="local", decision="approve")

        outcomes = []
        worker.finished.connect(lambda o: outcomes.append(o))
        worker.run()

        self.assertEqual(len(outcomes), 1)
        outcome = outcomes[0]
        self.assertIsNone(outcome.error)
        result = outcome.result
        self.assertIsNotNone(result)

        # ── 4. Check extraction populated ──────────────────────────────────
        extraction_data = {
            "fields": {},
        }
        for name, field in result.extraction.fields.items():
            extraction_data["fields"][name] = {
                "value": field.value,
                "confidence": field.confidence,
            }
        window._extraction_view.setPlainText(json.dumps(extraction_data, indent=2, default=str))
        extraction_text = window._extraction_view.toPlainText()
        self.assertIn("fields", extraction_text)

        # ── 5. Check validation populated ──────────────────────────────────
        validation_lines = []
        for v in result.validation:
            icon = {"PASS": "✓", "WARNING": "⚠", "FAIL": "✗"}.get(v.status, "?")
            validation_lines.append(f"{icon} {v.rule_id} — {v.message}")
        window._validation_view.setPlainText("\n".join(validation_lines))
        validation_text = window._validation_view.toPlainText()
        self.assertTrue(len(validation_text) > 0)

        # ── 6. Check decision populated ────────────────────────────────────
        decision_data = {
            "status": result.status,
            "reason": result.decision.reason,
            "human_reviewed": result.decision.human_reviewed,
        }
        window._decision_view.setPlainText(json.dumps(decision_data, indent=2))
        decision_text = window._decision_view.toPlainText()
        self.assertIn("APPROVED_BY_HUMAN", decision_text)

        # ── 7. Check evidence populated ────────────────────────────────────
        evidence_path = Path(outcome.evidence_path)
        self.assertTrue(evidence_path.exists())
        window._evidence_view.setPlainText(evidence_path.read_text(encoding="utf-8"))
        evidence_text = window._evidence_view.toPlainText()
        self.assertIn("trustdocs.evidence/1", evidence_text)
        self.assertIn("record_sha256", evidence_text)

        # ── 8. Verify evidence ─────────────────────────────────────────────
        from trustdocs.evidence import read_record

        record = read_record(evidence_path)
        valid, errors = record.verify()
        self.assertTrue(valid, f"Evidence verification failed: {errors}")

        # ── 9. Run tamper demo ─────────────────────────────────────────────
        tampered_dict = record.to_dict()
        tampered_dict["nodes"][0]["operation"] = "TAMPERED_document"
        tampered_dict["decision"] = "TAMPERED"

        from trustdocs.evidence import EvidenceNode, EvidenceRecord

        tampered_nodes = tuple(EvidenceNode(**n) for n in tampered_dict["nodes"])
        tampered_rec = EvidenceRecord(
            tampered_dict["execution_id"],
            tampered_nodes,
            tampered_dict["decision"],
            tampered_dict["record_sha256"],
        )
        valid2, errors2 = tampered_rec.verify()
        self.assertFalse(valid2, "Tampered evidence should be INVALID")
        self.assertTrue(len(errors2) > 0, "Should have verification errors")

        # ── 10. Display tamper result ──────────────────────────────────────
        tamper_output = (
            f"Original:  VALID\n"
            f"Tampered:  INVALID\n"
            f"Errors:    {'; '.join(errors2)}\n"
        )
        window._tamper_view.setPlainText(tamper_output)
        tamper_text = window._tamper_view.toPlainText()
        self.assertIn("VALID", tamper_text)
        self.assertIn("INVALID", tamper_text)

        window.close()

    def test_ledger_verify_flow(self):
        """Test ledger creation and verification through the GUI path."""
        if not SAMPLE.exists():
            self.skipTest("sample/invoice.pdf not found")

        from trustdocs.gui.main_window import MainWindow
        from trustdocs.gui.worker import PipelineWorker
        from trustdocs.evidence import read_record
        from trustdocs.ledger import Ledger, verify_ledger

        window = MainWindow()

        with TemporaryDirectory() as tmpdir:
            ledger_path = Path(tmpdir) / "test_ledger.jsonl"

            # Process document with ledger
            worker = PipelineWorker()
            worker.set_params(
                SAMPLE, extractor="local", decision="approve",
                ledger_path=ledger_path,
            )
            outcomes = []
            worker.finished.connect(lambda o: outcomes.append(o))
            worker.run()

            self.assertEqual(len(outcomes), 1)
            self.assertIsNone(outcomes[0].error)

            # Verify ledger exists and has 1 entry
            self.assertTrue(ledger_path.exists())
            ledger = Ledger(ledger_path)
            entries = ledger.entries()
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0].decision, "APPROVED_BY_HUMAN")

            # Verify ledger chain
            valid, errors = verify_ledger(ledger_path)
            self.assertTrue(valid, f"Ledger verification failed: {errors}")

            # Process a second document to chain
            worker2 = PipelineWorker()
            worker2.set_params(
                SAMPLE, extractor="local", decision="reject",
                ledger_path=ledger_path,
            )
            outcomes2 = []
            worker2.finished.connect(lambda o: outcomes2.append(o))
            worker2.run()

            # Verify chain grew
            entries2 = ledger.entries()
            self.assertEqual(len(entries2), 2)
            self.assertEqual(entries2[1].prev_entry_sha256, entries2[0].entry_sha256)

            # Verify head
            head = ledger.head()
            self.assertIsNotNone(head)
            self.assertEqual(head, entries2[1].entry_sha256)

            # Verify with anchor
            valid2, errors2 = verify_ledger(ledger_path, expected_head=head)
            self.assertTrue(valid2)

            window.close()


@unittest.skipUnless(HAS_PYSIDE6, _skip_reason)
class GuiWorkerTests(unittest.TestCase):
    """Test the pipeline worker in isolation."""

    def test_worker_produces_outcome(self):
        from trustdocs.gui.worker import PipelineWorker

        if not SAMPLE.exists():
            self.skipTest("sample/invoice.pdf not found")

        worker = PipelineWorker()
        worker.set_params(SAMPLE, extractor="local", decision="approve")

        results = []
        worker.finished.connect(lambda outcome: results.append(outcome))
        worker.run()

        self.assertEqual(len(results), 1)
        outcome = results[0]
        self.assertIsNone(outcome.error)
        self.assertIsNotNone(outcome.result)
        self.assertEqual(outcome.result.status, "APPROVED_BY_HUMAN")

    def test_worker_handles_missing_file(self):
        from trustdocs.gui.worker import PipelineWorker

        worker = PipelineWorker()
        worker.set_params(Path("nonexistent.pdf"), extractor="local")

        results = []
        worker.finished.connect(lambda outcome: results.append(outcome))
        worker.run()

        self.assertEqual(len(results), 1)
        self.assertIsNotNone(results[0].error)

    def test_worker_reject_decision(self):
        from trustdocs.gui.worker import PipelineWorker

        if not SAMPLE.exists():
            self.skipTest("sample/invoice.pdf not found")

        worker = PipelineWorker()
        worker.set_params(SAMPLE, extractor="local", decision="reject")

        results = []
        worker.finished.connect(lambda outcome: results.append(outcome))
        worker.run()

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].result.status, "REJECTED")

    def test_worker_auto_decision(self):
        from trustdocs.gui.worker import PipelineWorker

        if not SAMPLE.exists():
            self.skipTest("sample/invoice.pdf not found")

        worker = PipelineWorker()
        worker.set_params(SAMPLE, extractor="local", decision=None)

        results = []
        worker.finished.connect(lambda outcome: results.append(outcome))
        worker.run()

        self.assertEqual(len(results), 1)
        # Local adapter has no confidence -> forces human review
        self.assertIn(results[0].result.status, ("APPROVED_BY_HUMAN", "REJECTED"))


if __name__ == "__main__":
    unittest.main()
