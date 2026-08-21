"""Main window of the Trustworthy Document Pipeline GUI."""
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Slot
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..evidence import read_record
from .worker import (
    LedgerVerifyWorker,
    PipelineWorker,
    ProcessOutcome,
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

        # ── Tabs: Extraction | Validation | Decision | Evidence ────────────
        self._tabs = QTabWidget()

        self._tabs.addTab(self._build_extraction_tab(), "Extraction")
        self._tabs.addTab(self._build_validation_tab(), "Validation")
        self._tabs.addTab(self._build_decision_tab(), "Decision")
        self._tabs.addTab(self._build_evidence_tab(), "Evidence")
        self._tabs.addTab(self._build_tamper_tab(), "Tamper Demo")

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
            "Tamper Demo: modifies a copy of the evidence and verifies it.\n"
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

    def _connect_signals(self):
        self._select_btn.clicked.connect(self._on_select)
        self._process_btn.clicked.connect(self._on_process)
        self._verify_btn.clicked.connect(self._on_verify)
        self._ledger_verify_btn.clicked.connect(self._on_ledger_verify)
        self._export_btn.clicked.connect(self._on_export)
        self._tamper_btn.clicked.connect(self._on_tamper)

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

    @Slot()
    def _on_select(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Document",
            "",
            "Documents (*.pdf *.png *.jpg *.jpeg *.tif *.tiff *.docx *.xlsx *.pptx);;All Files (*)",
        )
        if path:
            self._document_path = Path(path)
            self._doc_label.setText(self._document_path.name)
            self._doc_label.setStyleSheet(f"color: {COLORS['text']};")
            self._process_btn.setEnabled(True)
            self._status_bar.showMessage(f"Selected: {self._document_path.name}")

            evidence_path = self._document_path.with_suffix(
                self._document_path.suffix + ".evidence.json"
            )
            if evidence_path.exists():
                self._evidence_path = evidence_path
                self._verify_btn.setEnabled(True)
                self._tamper_btn.setEnabled(True)
                self._status_bar.showMessage(
                    f"{self._document_path.name} (evidence exists)"
                )

    @Slot()
    def _on_process(self):
        if not self._document_path:
            return

        self._set_status("working")
        self._process_btn.setEnabled(False)
        self._log.clear()

        self._worker = PipelineWorker()
        self._worker_thread = QThread()
        self._worker.moveToThread(self._worker_thread)

        self._worker.log_message.connect(self._on_log)
        self._worker.finished.connect(self._on_process_done)

        self._worker_thread.started.connect(
            lambda: self._worker.run()
        )
        self._worker.finished.connect(self._worker_thread.quit)

        self._worker.set_params(
            self._document_path,
            extractor=self._extractor_combo.currentText(),
            decision=self._decision_combo.currentText()
            if self._decision_combo.currentText() != "auto"
            else None,
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

        # `_on_export` guards on `_last_result`, so this is exactly the moment
        # the button becomes usable. Without this it never did: the control was
        # wired to a handler and disabled at startup, and nothing switched it on.
        self._export_btn.setEnabled(True)

        # Update extraction tab
        extraction_data = {
            "extractor": self._extractor_combo.currentText(),
            "document_confidence": result.extraction.document_confidence,
            "fields": {},
        }
        for name, field in result.extraction.fields.items():
            extraction_data["fields"][name] = {
                "value": field.value,
                "confidence": field.confidence,
                "provenance": field.provenance,
            }
        self._extraction_view.setPlainText(
            json.dumps(extraction_data, indent=2, default=str)
        )

        # Update validation tab
        validation_lines = []
        for v in result.validation:
            icon = {"PASS": "✓", "WARNING": "⚠", "FAIL": "✗"}.get(v.status, "?")
            validation_lines.append(f"{icon} {v.rule_id} — {v.message}")
        if not validation_lines:
            validation_lines.append("No validation rules triggered.")
        self._validation_view.setPlainText("\n".join(validation_lines))

        # Update decision tab
        decision_data = {
            "status": result.status,
            "reason": result.decision.reason,
            "triggered_rules": list(result.decision.triggered_rules),
            "confidence": result.decision.confidence,
            "human_reviewed": result.decision.human_reviewed,
            "approved": result.decision.approved,
        }
        self._decision_view.setPlainText(json.dumps(decision_data, indent=2))

        # Update evidence tab
        if self._evidence_path and self._evidence_path.exists():
            self._evidence_view.setPlainText(
                self._evidence_path.read_text(encoding="utf-8")
            )
            self._verify_btn.setEnabled(True)
            self._tamper_btn.setEnabled(True)

        # Update ledger
        ledger_path = self._document_path.parent / "ledger.jsonl"
        if ledger_path.exists():
            self._ledger_verify_btn.setEnabled(True)
            self._ledger_path = ledger_path

        status = result.status
        if "REJECT" in status:
            self._set_status("error", status)
        elif "REVIEW" in status or "HUMAN" in status:
            self._set_status("working", status)
        else:
            self._set_status("verified", status)

        self._status_bar.showMessage(
            f"{self._document_path.name} — {status}"
        )

    @Slot()
    def _on_verify(self):
        if not self._evidence_path or not self._evidence_path.exists():
            return

        self._verify_btn.setEnabled(False)
        self._set_status("working")

        self._verify_worker = VerifyWorker()
        self._verify_thread = QThread()
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
                self._log.appendPlainText(f"  ✗ {err}")

        # Update evidence tab with verification result
        current = self._evidence_view.toPlainText()
        if valid:
            self._evidence_view.setPlainText(current + "\n\n✓ VERIFIED — integrity intact")
        else:
            self._evidence_view.setPlainText(
                current + "\n\n✗ INVALID — " + "; ".join(errors)
            )

    @Slot()
    def _on_ledger_verify(self):
        if not self._ledger_path or not self._ledger_path.exists():
            return

        self._ledger_verify_btn.setEnabled(False)
        self._set_status("working")

        self._ledger_worker = LedgerVerifyWorker()
        self._ledger_thread = QThread()
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
                self._log.appendPlainText(f"  ✗ {err}")

    @Slot()
    def _on_export(self):
        if not self._last_result:
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Evidence",
            str(self._evidence_path) if self._evidence_path else "evidence.json",
            "JSON Files (*.json);;All Files (*)",
        )
        if path:
            from ..evidence import write_record

            write_record(Path(path), self._last_result.evidence)
            self._status_bar.showMessage(f"Exported to {path}")

    @Slot()
    def _on_tamper(self):
        if not self._evidence_path or not self._evidence_path.exists():
            return


        self._tamper_view.clear()
        self._tamper_view.appendPlainText("=" * 50)
        self._tamper_view.appendPlainText("  TAMPER DEMO")
        self._tamper_view.appendPlainText("=" * 50)
        self._tamper_view.appendPlainText("")

        try:
            record = read_record(self._evidence_path)

            # Step 1: Verify original
            self._tamper_view.appendPlainText("Step 1: Verify original evidence")
            valid, errors = record.verify()
            status = "VALID" if valid else "INVALID"
            self._tamper_view.appendPlainText(f"  Result: {status}")
            self._tamper_view.appendPlainText("")

            # Step 2: Create tampered copy
            self._tamper_view.appendPlainText("Step 2: Create tampered copy (flip 1 byte)")
            tampered_dict = record.to_dict()
            nodes = tampered_dict["nodes"]
            if nodes:
                node = nodes[0]
                node["operation"] = "TAMPERED_" + node.get("operation", "unknown")
            tampered_dict["decision"] = "TAMPERED"

            # Step 3: Verify tampered
            self._tamper_view.appendPlainText("Step 3: Verify tampered evidence")
            from ..evidence import EvidenceNode, EvidenceRecord

            tampered_nodes = tuple(
                EvidenceNode(**n) for n in tampered_dict["nodes"]
            )
            tampered_rec = EvidenceRecord(
                tampered_dict["execution_id"],
                tampered_nodes,
                tampered_dict["decision"],
                tampered_dict["record_sha256"],
            )
            valid2, errors2 = tampered_rec.verify()
            status2 = "VALID" if valid2 else "INVALID"
            self._tamper_view.appendPlainText(f"  Result: {status2}")
            if errors2:
                for err in errors2:
                    self._tamper_view.appendPlainText(f"  ✗ {err}")
            self._tamper_view.appendPlainText("")

            # Step 4: Summary
            self._tamper_view.appendPlainText("=" * 50)
            self._tamper_view.appendPlainText("  SUMMARY")
            self._tamper_view.appendPlainText("=" * 50)
            self._tamper_view.appendPlainText(f"  Original:  {status}")
            self._tamper_view.appendPlainText(f"  Tampered:  {status2}")
            self._tamper_view.appendPlainText("")
            if valid and not valid2:
                self._tamper_view.appendPlainText(
                    "  ✓ Tamper-evident: the system correctly detects alteration."
                )
            elif not valid and not valid2:
                self._tamper_view.appendPlainText(
                    "  Both invalid — original evidence may already be corrupted."
                )
            else:
                self._tamper_view.appendPlainText(
                    "  ⚠ Unexpected: tampered evidence passed verification."
                )
            self._tamper_view.appendPlainText("")

        except Exception as exc:
            self._tamper_view.appendPlainText(f"ERROR: {exc}")

    @Slot(str)
    def _on_log(self, message: str):
        self._log.appendPlainText(message)
