"""Main window of the Trustworthy Document Pipeline GUI."""
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt, QThread, QTimer, Slot
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..evidence import write_record
from .worker import (
    LedgerVerifyWorker,
    PipelineWorker,
    ProcessOutcome,
    TamperWorker,
    VerifyWorker,
)

MONOSPACE = QFont("Consolas", 11)
MONOSPACE.setStyleHint(QFont.StyleHint.Monospace)

COLORS = {
    "bg": "#1e1e1e",
    "surface": "#252526",
    "border": "#3c3c3c",
    "text": "#d4d4d4",
    "text_dim": "#808080",
    "green": "#4ec9b0",
    "red": "#f44747",
    "yellow": "#dcdcaa",
    "blue": "#569cd6",
    "orange": "#ce9178",
    "status_ready": "#4ec9b0",
    "status_working": "#569cd6",
    "status_error": "#f44747",
}

STYLESHEET = f"""
QMainWindow {{
    background-color: {COLORS['bg']};
}}
QWidget {{
    color: {COLORS['text']};
    font-family: 'Segoe UI', sans-serif;
    font-size: 12px;
}}
QGroupBox {{
    border: 1px solid {COLORS['border']};
    border-radius: 4px;
    margin-top: 12px;
    padding-top: 16px;
    font-weight: bold;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 6px;
}}
QPushButton {{
    background-color: {COLORS['surface']};
    border: 1px solid {COLORS['border']};
    border-radius: 4px;
    padding: 6px 14px;
    font-weight: bold;
}}
QPushButton:hover {{
    background-color: {COLORS['border']};
}}
QPushButton:pressed {{
    background-color: #505050;
}}
QPushButton:disabled {{
    color: {COLORS['text_dim']};
}}
QComboBox {{
    background-color: {COLORS['surface']};
    border: 1px solid {COLORS['border']};
    border-radius: 4px;
    padding: 4px 8px;
}}
QTabWidget::pane {{
    border: 1px solid {COLORS['border']};
    border-radius: 4px;
}}
QTabBar::tab {{
    background-color: {COLORS['surface']};
    border: 1px solid {COLORS['border']};
    border-bottom: none;
    border-radius: 4px 4px 0 0;
    padding: 6px 12px;
}}
QTabBar::tab:selected {{
    background-color: {COLORS['bg']};
}}
QPlainTextEdit {{
    background-color: {COLORS['surface']};
    border: 1px solid {COLORS['border']};
    border-radius: 4px;
    font-family: Consolas, monospace;
    font-size: 11px;
}}
QStatusBar {{
    background-color: {COLORS['surface']};
    border-top: 1px solid {COLORS['border']};
}}
QLabel {{
    font-size: 12px;
}}
"""


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Trustworthy Document Pipeline")
        self.setMinimumSize(900, 640)
        self.resize(1100, 720)
        self.setStyleSheet(STYLESHEET)

        self._document_path: Path | None = None
        self._evidence_path: Path | None = None
        self._ledger_path: Path | None = None
        self._last_result = None

        self._worker_thread: QThread | None = None
        self._worker: PipelineWorker | None = None
        self._threads: list[QThread] = []

        self._self_test_queue: list = []
        self._self_test_pass = 0
        self._self_test_total = 0
        self._self_test_session = None

        self._build_ui()
        self._connect_signals()
        self._set_status("ready")

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # ── Toolbar ────────────────────────────────────────────────────────
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)

        toolbar.addWidget(QLabel("Extractor:"))
        self._extractor_combo = QComboBox()
        self._extractor_combo.addItems(["local", "nutrient"])
        self._extractor_combo.setMinimumWidth(100)
        toolbar.addWidget(self._extractor_combo)

        toolbar.addWidget(QLabel("Decision:"))
        self._decision_combo = QComboBox()
        self._decision_combo.addItems(["auto", "approve", "reject"])
        self._decision_combo.setMinimumWidth(80)
        toolbar.addWidget(self._decision_combo)

        toolbar.addStretch()

        self._status_label = QLabel("● Ready")
        self._status_label.setStyleSheet(f"color: {COLORS['status_ready']}; font-weight: bold;")
        toolbar.addWidget(self._status_label)

        layout.addLayout(toolbar)

        # ── Document + Action bar ──────────────────────────────────────────
        doc_bar = QHBoxLayout()
        doc_bar.setSpacing(8)

        self._select_btn = QPushButton("Select PDF")
        self._select_btn.setMinimumWidth(100)
        doc_bar.addWidget(self._select_btn)

        self._doc_label = QLabel("No document selected")
        self._doc_label.setStyleSheet(f"color: {COLORS['text_dim']};")
        doc_bar.addWidget(self._doc_label, 1)

        self._process_btn = QPushButton("Process")
        self._process_btn.setMinimumWidth(100)
        self._process_btn.setEnabled(False)
        doc_bar.addWidget(self._process_btn)

        layout.addLayout(doc_bar)

        # ── Main splitter ──────────────────────────────────────────────────
        splitter = QSplitter(Qt.Orientation.Vertical)

        # ── Tabs ───────────────────────────────────────────────────────────
        self._tabs = QTabWidget()

        self._tabs.addTab(self._build_extraction_tab(), "Extraction")
        self._tabs.addTab(self._build_validation_tab(), "Validation")
        self._tabs.addTab(self._build_decision_tab(), "Decision")
        self._tabs.addTab(self._build_evidence_tab(), "Evidence")
        self._tabs.addTab(self._build_tamper_tab(), "Tamper Demo")
        self._tabs.addTab(self._build_diagnostics_tab(), "Diagnostics")

        splitter.addWidget(self._tabs)

        # ── Log panel ──────────────────────────────────────────────────────
        log_group = QGroupBox("Trace")
        log_layout = QVBoxLayout(log_group)
        log_layout.setContentsMargins(4, 4, 4, 4)
        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumBlockCount(200)
        self._log.setFont(MONOSPACE)
        self._log.setMaximumHeight(160)
        log_layout.addWidget(self._log)
        splitter.addWidget(log_group)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)

        layout.addWidget(splitter, 1)

        # ── Bottom action bar ──────────────────────────────────────────────
        bottom_bar = QHBoxLayout()
        bottom_bar.setSpacing(8)

        self._verify_btn = QPushButton("Verify Evidence")
        self._verify_btn.setEnabled(False)
        bottom_bar.addWidget(self._verify_btn)

        self._ledger_verify_btn = QPushButton("Verify Ledger")
        self._ledger_verify_btn.setEnabled(False)
        bottom_bar.addWidget(self._ledger_verify_btn)

        bottom_bar.addStretch()

        self._export_btn = QPushButton("Export")
        self._export_btn.setEnabled(False)
        bottom_bar.addWidget(self._export_btn)

        layout.addLayout(bottom_bar)

        # ── Status bar ─────────────────────────────────────────────────────
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._status_bar.showMessage("Ready")

    def _build_extraction_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(4, 4, 4, 4)

        self._extraction_view = QPlainTextEdit()
        self._extraction_view.setReadOnly(True)
        self._extraction_view.setFont(MONOSPACE)
        self._extraction_view.setPlaceholderText("Process a document to see extraction results...")
        layout.addWidget(self._extraction_view)

        return widget

    def _build_validation_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(4, 4, 4, 4)

        self._validation_view = QPlainTextEdit()
        self._validation_view.setReadOnly(True)
        self._validation_view.setFont(MONOSPACE)
        self._validation_view.setPlaceholderText("Process a document to see validation results...")
        layout.addWidget(self._validation_view)

        return widget

    def _build_decision_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(4, 4, 4, 4)

        self._decision_view = QPlainTextEdit()
        self._decision_view.setReadOnly(True)
        self._decision_view.setFont(MONOSPACE)
        self._decision_view.setPlaceholderText("Process a document to see the decision...")
        layout.addWidget(self._decision_view)

        return widget

    def _build_evidence_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(4, 4, 4, 4)

        self._evidence_view = QPlainTextEdit()
        self._evidence_view.setReadOnly(True)
        self._evidence_view.setFont(MONOSPACE)
        self._evidence_view.setPlaceholderText("Process a document to see evidence...")
        layout.addWidget(self._evidence_view)

        return widget

    def _build_tamper_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(4, 4, 4, 4)

        info = QLabel(
            "Tamper Demo: modifies an in-memory copy of the evidence and verifies it.\n"
            "Original files are never touched."
        )
        info.setStyleSheet(f"color: {COLORS['text_dim']};")
        info.setWordWrap(True)
        layout.addWidget(info)

        btn_bar = QHBoxLayout()
        self._tamper_btn = QPushButton("Run Tamper Demo")
        self._tamper_btn.setEnabled(False)
        btn_bar.addWidget(self._tamper_btn)
        btn_bar.addStretch()
        layout.addLayout(btn_bar)

        self._tamper_view = QPlainTextEdit()
        self._tamper_view.setReadOnly(True)
        self._tamper_view.setFont(MONOSPACE)
        self._tamper_view.setPlaceholderText("Process a document first, then run the tamper demo...")
        layout.addWidget(self._tamper_view)

        return widget

    def _build_diagnostics_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(4, 4, 4, 4)

        info = QLabel(
            "Runs every button's code path end-to-end against a disposable document:\n"
            "selection state machine, pipeline worker, tab population, evidence verify,\n"
            "tamper detection, ledger write+verify, export and corruption detection.\n"
            "Your current session is not modified."
        )
        info.setStyleSheet(f"color: {COLORS['text_dim']};")
        info.setWordWrap(True)
        layout.addWidget(info)

        btn_bar = QHBoxLayout()
        self._selftest_btn = QPushButton("Run Self-Test")
        btn_bar.addWidget(self._selftest_btn)
        btn_bar.addStretch()
        layout.addLayout(btn_bar)

        self._selftest_view = QPlainTextEdit()
        self._selftest_view.setReadOnly(True)
        self._selftest_view.setFont(MONOSPACE)
        self._selftest_view.setPlaceholderText(
            "Click Run Self-Test to audit every button behaviour..."
        )
        layout.addWidget(self._selftest_view)

        return widget

    def _connect_signals(self):
        self._select_btn.clicked.connect(self._on_select)
        self._process_btn.clicked.connect(self._on_process)
        self._verify_btn.clicked.connect(self._on_verify)
        self._ledger_verify_btn.clicked.connect(self._on_ledger_verify)
        self._export_btn.clicked.connect(self._on_export)
        self._tamper_btn.clicked.connect(self._on_tamper)
        self._selftest_btn.clicked.connect(self._on_self_test)

    def closeEvent(self, event):
        for thread in self._threads:
            thread.quit()
            thread.wait(2000)
        event.accept()

    def _set_status(self, state: str, message: str = ""):
        if state == "ready":
            self._status_label.setText("● Ready")
            self._status_label.setStyleSheet(
                f"color: {COLORS['status_ready']}; font-weight: bold;"
            )
        elif state == "working":
            self._status_label.setText("● Working...")
            self._status_label.setStyleSheet(
                f"color: {COLORS['status_working']}; font-weight: bold;"
            )
        elif state == "error":
            self._status_label.setText(f"● Error: {message}")
            self._status_label.setStyleSheet(
                f"color: {COLORS['status_error']}; font-weight: bold;"
            )
        elif state == "verified":
            self._status_label.setText("● Verified")
            self._status_label.setStyleSheet(
                f"color: {COLORS['green']}; font-weight: bold;"
            )

    def _feedback(self, message: str):
        self._log.appendPlainText(message)
        self._status_bar.showMessage(message)

    @Slot()
    def _on_select(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Document",
            "",
            "Documents (*.pdf *.png *.jpg *.jpeg *.tif *.tiff *.docx *.xlsx *.pptx);;All Files (*)",
        )
        if path:
            self._apply_selected_document(Path(path))

    def _apply_selected_document(self, path: Path):
        self._document_path = path
        self._last_result = None
        self._evidence_path = None
        self._ledger_path = None

        self._doc_label.setText(path.name)
        self._doc_label.setStyleSheet(f"color: {COLORS['text']};")
        self._process_btn.setEnabled(True)
        self._export_btn.setEnabled(False)
        self._verify_btn.setEnabled(False)
        self._tamper_btn.setEnabled(False)
        self._ledger_verify_btn.setEnabled(False)

        for view in (
            self._extraction_view,
            self._validation_view,
            self._decision_view,
            self._evidence_view,
            self._tamper_view,
        ):
            view.clear()

        sidecar = path.with_suffix(path.suffix + ".evidence.json")
        if sidecar.exists():
            self._evidence_path = sidecar
            self._verify_btn.setEnabled(True)
            self._tamper_btn.setEnabled(True)

        ledger = path.parent / "ledger.jsonl"
        if ledger.exists():
            self._ledger_path = ledger
            self._ledger_verify_btn.setEnabled(True)

        self._set_status("ready")
        message = f"Selected: {path.name}"
        if self._evidence_path:
            message += " (evidence exists)"
        self._status_bar.showMessage(message)

    @Slot()
    def _on_process(self):
        if not self._document_path:
            self._feedback("Select a document first.")
            return

        self._set_status("working")
        self._process_btn.setEnabled(False)
        self._log.clear()

        self._worker = PipelineWorker()
        self._worker_thread = QThread(self)
        self._threads.append(self._worker_thread)
        self._worker.moveToThread(self._worker_thread)

        self._worker.log_message.connect(self._on_log)
        self._worker.finished.connect(self._on_process_done)

        self._worker_thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._worker_thread.quit)

        self._worker.set_params(
            self._document_path,
            extractor=self._extractor_combo.currentText(),
            decision=self._decision_combo.currentText()
            if self._decision_combo.currentText() != "auto"
            else None,
            ledger_path=self._document_path.parent / "ledger.jsonl",
        )

        self._worker_thread.start()

    @Slot(object)
    def _on_process_done(self, outcome: ProcessOutcome):
        self._process_btn.setEnabled(True)

        if outcome.error:
            self._set_status("error", outcome.error)
            self._log.appendPlainText(f"ERROR: {outcome.error}")
            return

        result = outcome.result
        if not result:
            self._set_status("error", "No result")
            return

        self._last_result = result
        self._evidence_path = Path(outcome.evidence_path) if outcome.evidence_path else None

        self._export_btn.setEnabled(True)

        extraction_data = {
            "extractor": self._extractor_combo.currentText(),
            "document_confidence": result.extraction.document_confidence,
            "fields": {},
        }
        for name, field in result.extraction.fields.items():
            field_info: dict = {
                "value": field.value,
                "confidence": field.confidence,
                "provenance": field.provenance,
            }
            citation = (field.provenance or {}).get("citation")
            if citation and isinstance(citation, dict):
                field_info["citation"] = {
                    "page": citation.get("page"),
                    "box": citation.get("box"),
                    "source": citation.get("source"),
                }
            extraction_data["fields"][name] = field_info
        self._extraction_view.setPlainText(
            json.dumps(extraction_data, indent=2, default=str)
        )

        validation_lines = []
        for v in result.validation:
            icon = {"PASS": "OK", "WARNING": "!", "FAIL": "X"}.get(v.status, "?")
            validation_lines.append(f"{icon} {v.rule_id} - {v.message}")
        if not validation_lines:
            validation_lines.append("No validation rules triggered.")
        self._validation_view.setPlainText("\n".join(validation_lines))

        decision_data = {
            "status": result.status,
            "reason": result.decision.reason,
            "triggered_rules": list(result.decision.triggered_rules),
            "confidence": result.decision.confidence,
            "human_reviewed": result.decision.human_reviewed,
            "approved": result.decision.approved,
        }
        if result.decision.review:
            review = result.decision.review
            decision_data["review"] = {
                "review_id": review.review_id,
                "timestamp": review.timestamp,
                "reviewer": review.reviewer,
                "decision": review.decision,
                "reason_code": review.reason_code,
                "extraction_hash": review.extraction_hash,
            }
        self._decision_view.setPlainText(json.dumps(decision_data, indent=2))

        if self._evidence_path and self._evidence_path.exists():
            self._evidence_view.setPlainText(
                self._evidence_path.read_text(encoding="utf-8")
            )
            self._verify_btn.setEnabled(True)
            self._tamper_btn.setEnabled(True)

        if self._document_path is not None:
            ledger_dir = self._document_path.parent
        elif self._evidence_path is not None:
            ledger_dir = self._evidence_path.parent
        else:
            ledger_dir = None
        if ledger_dir is not None:
            ledger_path = ledger_dir / "ledger.jsonl"
            if ledger_path.exists():
                self._ledger_path = ledger_path
                self._ledger_verify_btn.setEnabled(True)

        status = result.status
        if "REJECT" in status:
            self._set_status("error", status)
        elif "REVIEW" in status or "HUMAN" in status:
            self._set_status("working", status)
        else:
            self._set_status("verified", status)

        self._status_bar.showMessage(
            f"{self._document_path.name} - {status}"
            if self._document_path
            else f"{status}"
        )

    @Slot()
    def _on_verify(self):
        if not self._evidence_path or not self._evidence_path.exists():
            self._feedback("No evidence to verify yet — process a document first.")
            return

        self._verify_btn.setEnabled(False)
        self._set_status("working")

        self._verify_worker = VerifyWorker()
        self._verify_thread = QThread(self)
        self._threads.append(self._verify_thread)
        self._verify_worker.moveToThread(self._verify_thread)

        self._verify_worker.finished.connect(self._on_verify_done)
        self._verify_worker.set_params(self._evidence_path)

        self._verify_thread.started.connect(self._verify_worker.run)
        self._verify_worker.finished.connect(self._verify_thread.quit)

        self._verify_thread.start()

    @Slot(bool, list)
    def _on_verify_done(self, valid: bool, errors: list):
        self._verify_btn.setEnabled(True)

        if valid:
            self._set_status("verified")
            self._log.appendPlainText("Evidence verification: VALID")
        else:
            self._set_status("error", "INVALID")
            for err in errors:
                self._log.appendPlainText(f"  X {err}")

        current = self._evidence_view.toPlainText()
        if valid:
            self._evidence_view.setPlainText(current + "\n\nVERIFIED - integrity intact")
        else:
            self._evidence_view.setPlainText(
                current + "\n\nINVALID - " + "; ".join(errors)
            )

    @Slot()
    def _on_ledger_verify(self):
        if not self._ledger_path or not self._ledger_path.exists():
            self._feedback("No ledger found yet — process a document first.")
            return

        self._ledger_verify_btn.setEnabled(False)
        self._set_status("working")

        self._ledger_worker = LedgerVerifyWorker()
        self._ledger_thread = QThread(self)
        self._threads.append(self._ledger_thread)
        self._ledger_worker.moveToThread(self._ledger_thread)

        self._ledger_worker.finished.connect(self._on_ledger_verify_done)
        self._ledger_worker.set_params(self._ledger_path)

        self._ledger_thread.started.connect(self._ledger_worker.run)
        self._ledger_worker.finished.connect(self._ledger_thread.quit)

        self._ledger_thread.start()

    @Slot(bool, list, int)
    def _on_ledger_verify_done(self, valid: bool, errors: list, entry_count: int):
        self._ledger_verify_btn.setEnabled(True)

        if valid:
            self._set_status("verified")
            self._log.appendPlainText(f"Ledger verification: VALID ({entry_count} entries)")
        else:
            self._set_status("error", "INVALID")
            for err in errors:
                self._log.appendPlainText(f"  X {err}")

    @Slot()
    def _on_export(self):
        if not self._last_result:
            self._feedback("Nothing to export yet — process a document first.")
            return

        default = str(self._evidence_path) if self._evidence_path else "evidence.json"
        if not default.lower().endswith(".json"):
            default += ".json"

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Evidence",
            default,
            "JSON Files (*.json);;All Files (*)",
        )
        if not path:
            return

        try:
            exported = self._export_to(Path(path))
        except Exception as exc:
            QMessageBox.critical(self, "Export failed", f"{type(exc).__name__}: {exc}")
            return

        self._log.appendPlainText(f"Evidence exported: {exported}")
        self._status_bar.showMessage(f"Exported to {exported}")

    def _export_to(self, path: Path) -> Path:
        if path.suffix == "":
            path = path.with_suffix(".json")
        write_record(path, self._last_result.evidence)
        return path

    @Slot()
    def _on_tamper(self):
        if not self._evidence_path or not self._evidence_path.exists():
            self._feedback("No evidence yet — process a document first.")
            return

        self._tamper_btn.setEnabled(False)
        self._tamper_view.clear()
        self._set_status("working")

        self._tamper_worker = TamperWorker()
        self._tamper_thread = QThread(self)
        self._threads.append(self._tamper_thread)
        self._tamper_worker.moveToThread(self._tamper_thread)

        self._tamper_worker.step_line.connect(self._tamper_view.appendPlainText)
        self._tamper_worker.finished.connect(self._on_tamper_done)
        self._tamper_worker.set_params(self._evidence_path)

        self._tamper_thread.started.connect(self._tamper_worker.run)
        self._tamper_worker.finished.connect(self._tamper_thread.quit)

        self._tamper_thread.start()

    @Slot(bool, bool, list)
    def _on_tamper_done(self, original_valid: bool, tampered_valid: bool, errors: list):
        self._tamper_btn.setEnabled(True)
        if original_valid and not tampered_valid:
            self._set_status("verified", "tamper detection confirmed")
        else:
            self._set_status("error", "unexpected tamper demo result")

    @Slot(str)
    def _on_log(self, message: str):
        self._log.appendPlainText(message)

    @Slot()
    def _on_self_test(self):
        from .selftest import SelfTestSession

        self._self_test_session = SelfTestSession()
        self._selftest_btn.setEnabled(False)
        self._selftest_view.clear()
        checks = self._self_test_session.checks()
        self._self_test_queue = list(checks)
        self._self_test_pass = 0
        self._self_test_total = len(checks)
        self._set_status("working", "self-test")
        self._selftest_view.appendPlainText(
            f"Auditing {len(checks)} behaviours against a disposable window...\n"
        )
        QTimer.singleShot(0, self._run_next_self_test)

    @Slot()
    def _run_next_self_test(self):
        from .selftest import run_check

        if not self._self_test_queue:
            summary = (
                f"\n{'=' * 50}\n"
                f"SELF-TEST RESULT: {self._self_test_pass}/{self._self_test_total} passed"
            )
            self._selftest_view.appendPlainText(summary)
            self._selftest_btn.setEnabled(True)
            self._self_test_session.close()
            self._self_test_session = None
            if self._self_test_pass == self._self_test_total:
                self._set_status("verified", "all self-tests passed")
                self._status_bar.showMessage("Self-test: all checks passed")
            else:
                failed = self._self_test_total - self._self_test_pass
                self._set_status("error", f"{failed} self-tests failed")
            return

        check = self._self_test_queue.pop(0)
        result = run_check(self._self_test_session, check)
        mark = "PASS" if result.ok else "FAIL"
        line = f"[{mark}] {result.id} {result.title}"
        if result.detail:
            line += f" -- {result.detail}"
        self._selftest_view.appendPlainText(line)
        if result.ok:
            self._self_test_pass += 1
        QTimer.singleShot(0, self._run_next_self_test)
