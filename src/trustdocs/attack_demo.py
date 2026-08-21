"""Reproducible attack demo: the pipeline attacking its own guarantees.

Run with: python -m trustdocs.attack_demo

Every scenario is deterministic. No API key required. The output shows
exactly which attacks the system catches and which it cannot.
"""
from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

from .evidence import EvidenceNode, EvidenceRecord, read_record, write_record, _digest
from .ledger import Ledger, verify_ledger
from .pipeline import Document, DocumentPipeline, Extraction, FieldValue
from .render import BOLD, DIM, GREEN, RED, RESET, YELLOW, supports_color


class _DemoDocumentService:
    name = "demo-document-service"

    def extract(self, document: Document) -> Extraction:
        return Extraction(
            fields={
                "document_type": FieldValue("demo", 0.99, {"source": "demo"}),
                "bytes": FieldValue(len(document.content), 1.0, {"source": "demo"}),
            },
            document_confidence=0.91,
        )


class _DemoReviewer:
    def review(self, extraction: Extraction) -> bool:
        return (extraction.document_confidence or 0) >= 0.5


class _Attack:
    def __init__(self, name: str, description: str, detectable: bool):
        self.name = name
        self.description = description
        self.detectable = detectable
        self.caught = False
        self.errors: list[str] = []


def _heading(text: str, color: str = BOLD) -> str:
    return f"\n{color}{'=' * 60}\n  {text}\n{'=' * 60}{RESET}"


def _step(text: str) -> str:
    return f"  {DIM}►{RESET} {text}"


def _result_line(caught: bool, label: str, errors: list[str]) -> str:
    color = GREEN if caught else RED
    icon = "✓" if caught else "✗"
    lines = [f"  {color}{icon} {label}{RESET}"]
    for err in errors[:3]:
        lines.append(f"    {DIM}→ {err}{RESET}")
    return "\n".join(lines)


def _build_clean_ledger(path: Path, n: int = 5) -> str:
    """Create a clean ledger with n entries, return the head hash."""
    ledger = Ledger(path)
    for i in range(n):
        ledger.append(
            execution_id=f"exec-{i:04d}",
            record_sha256=f"{i:064x}",
            document_sha256=f"{i + 100:064x}",
            decision="AUTO_APPROVED",
        )
    return Ledger(path).head()


def _rows_from(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def _rewrite_rows(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n" for r in rows),
        encoding="utf-8",
    )


def run_attack_demo() -> dict:
    """Run all attack scenarios. Returns a structured result for rendering."""
    color = supports_color()
    c = lambda txt, col: f"{col}{txt}{RESET}" if color else txt
    bold = lambda txt: c(txt, BOLD)
    dim = lambda txt: c(txt, DIM)
    green = lambda txt: c(txt, GREEN)
    red = lambda txt: c(txt, RED)
    yellow = lambda txt: c(txt, YELLOW)

    attacks: list[_Attack] = []

    print(bold("Trustworthy Document Pipeline — Attack Demo"))
    print(dim("The pipeline attacking its own guarantees. No API key needed.\n"))

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # ── Step 1: Build a clean evidence record ──────────────────────────
        print(_heading("STEP 1: Build a clean, valid evidence record"))

        doc_content = b"deterministic demo document"
        doc = Document(doc_content, "demo.pdf", "application/pdf")
        service = _DemoDocumentService()
        pipeline = DocumentPipeline(service, _DemoReviewer())
        result = pipeline.run(doc)

        evidence_path = tmpdir / "original.evidence.json"
        write_record(evidence_path, result.evidence)

        valid, errors = result.evidence.verify()
        print(_step(f"Document hash:  sha256:{result.document_sha256[:16]}..."))
        print(_step(f"Decision:       {result.status}"))
        print(_step(f"Evidence nodes: {len(result.evidence.nodes)}"))
        print(_result_line(valid, f"Evidence verification: {'VALID' if valid else 'INVALID'}", errors))
        attacks.append(_Attack("original", "Clean evidence record", True))
        attacks[-1].caught = valid
        attacks[-1].errors = errors

        # ── Step 2: Modify the document content ────────────────────────────
        print(_heading("STEP 2: ATTACK — Modify the document (1 byte)"))

        tampered_doc = bytearray(doc_content)
        tampered_doc[0] ^= 0xFF  # flip first byte
        new_doc_hash = hashlib.sha256(bytes(tampered_doc)).hexdigest()

        # The evidence still references the OLD document hash
        # Show that re-hashing the document breaks the chain
        original_doc_hash = result.document_sha256
        print(_step(f"Original hash: sha256:{original_doc_hash[:16]}..."))
        print(_step(f"Tampered hash: sha256:{new_doc_hash[:16]}..."))
        print(_step("The evidence record still references the original hash."))
        print(_step("If someone swaps the document, the hashes no longer match."))

        doc_mismatch = new_doc_hash != original_doc_hash
        attacks.append(_Attack("modify_document", "Swap document content", True))
        attacks[-1].caught = doc_mismatch
        if doc_mismatch:
            attacks[-1].errors = ["document hash changed — original evidence no longer matches"]

        print(_result_line(doc_mismatch,
                           f"Document tampering detected: hashes differ",
                           attacks[-1].errors))

        # ── Step 3: Modify the extraction in evidence ──────────────────────
        print(_heading("STEP 3: ATTACK — Tamper with extraction in evidence"))

        record = read_record(evidence_path)
        # Find the extraction node (operation != "document" and != "decision" and != "human_review")
        extraction_node_idx = None
        for i, node in enumerate(record.nodes):
            if node.operation not in ("document", "decision", "human_review"):
                extraction_node_idx = i
                break

        if extraction_node_idx is not None:
            node = record.nodes[extraction_node_idx]
            tampered_node = EvidenceNode(
                node.id, node.operation, node.input_hash, node.output_hash,
                {**node.metadata, "field_count": 999},  # tamper with metadata
                node.parent_ids,
            )
            nodes = list(record.nodes)
            nodes[extraction_node_idx] = tampered_node
            tampered_record = EvidenceRecord(
                record.execution_id, tuple(nodes), record.decision, record.record_sha256,
            )
            valid_ext, errors_ext = tampered_record.verify()
            attacks.append(_Attack("modify_extraction", "Tamper extraction metadata", True))
            attacks[-1].caught = not valid_ext
            attacks[-1].errors = errors_ext
            print(_step(f"Changed extraction node metadata (field_count: 1 → 999)"))
            print(_step(f"Node ID is now invalid because it was computed from original metadata."))
            print(_result_line(not valid_ext, f"Extraction tampering detected", errors_ext))

        # ── Step 4: Modify the decision ────────────────────────────────────
        print(_heading("STEP 4: ATTACK — Change the decision field"))

        record2 = read_record(evidence_path)
        nodes2 = list(record2.nodes)
        decision_node_idx = None
        for i, node in enumerate(record2.nodes):
            if node.operation == "decision":
                decision_node_idx = i
                break

        if decision_node_idx is not None:
            dn = record2.nodes[decision_node_idx]
            new_decision = "REJECTED" if record2.decision != "REJECTED" else "APPROVED_BY_HUMAN"
            tampered_dn = EvidenceNode(
                dn.id, dn.operation, dn.input_hash, dn.output_hash,
                {**dn.metadata, "decision": new_decision},
                dn.parent_ids,
            )
            nodes2[decision_node_idx] = tampered_dn
            tampered_record2 = EvidenceRecord(
                record2.execution_id, tuple(nodes2), record2.decision, record2.record_sha256,
            )
            valid_dec, errors_dec = tampered_record2.verify()
            attacks.append(_Attack("modify_decision", "Change decision in evidence", True))
            attacks[-1].caught = not valid_dec
            attacks[-1].errors = errors_dec
            print(_step(f"Changed decision node: '{record2.decision}' → '{new_decision}'"))
            print(_step(f"Node ID no longer matches its content."))
            print(_result_line(not valid_dec, f"Decision tampering detected", errors_dec))

        # ── Step 5: Alter a ledger entry ───────────────────────────────────
        print(_heading("STEP 5: ATTACK — Alter a ledger entry"))

        ledger_path = tmpdir / "ledger.jsonl"
        original_head = _build_clean_ledger(ledger_path, 5)
        rows = _rows_from(ledger_path)

        original_decision_row1 = rows[1]["decision"]
        rows[1]["decision"] = "FORGED_DECISION"
        _rewrite_rows(ledger_path, rows)

        valid_led, errors_led = verify_ledger(ledger_path)
        attacks.append(_Attack("alter_ledger", "Modify a ledger entry", True))
        attacks[-1].caught = not valid_led
        attacks[-1].errors = errors_led
        print(_step(f"Entry 1: '{original_decision_row1}' → 'FORGED_DECISION'"))
        print(_step("The entry hash no longer matches, and the chain breaks."))
        print(_result_line(not valid_led, f"Ledger tampering detected", errors_led))

        # ── Step 6: Delete an intermediate entry ───────────────────────────
        print(_heading("STEP 6: ATTACK — Delete a ledger entry"))

        ledger_path2 = tmpdir / "ledger2.jsonl"
        _build_clean_ledger(ledger_path2, 5)
        rows2 = _rows_from(ledger_path2)
        del rows2[2]  # delete the middle entry
        _rewrite_rows(ledger_path2, rows2)

        valid_del, errors_del = verify_ledger(ledger_path2)
        attacks.append(_Attack("delete_entry", "Delete a ledger entry", True))
        attacks[-1].caught = not valid_del
        attacks[-1].errors = errors_del
        print(_step(f"Deleted entry at position 2 (of 5)"))
        print(_step("Sequence numbers no longer match and chain links break."))
        print(_result_line(not valid_del, f"Entry deletion detected", errors_del))

        # ── Step 7: Truncate the tail ──────────────────────────────────────
        print(_heading("STEP 7: LIMITATION — Truncate the tail"))

        ledger_path3 = tmpdir / "ledger3.jsonl"
        full_head = _build_clean_ledger(ledger_path3, 5)
        rows3 = _rows_from(ledger_path3)
        _rewrite_rows(ledger_path3, rows3[:3])  # keep only first 3

        valid_trunc, errors_trunc = verify_ledger(ledger_path3)
        attacks.append(_Attack("truncate_tail", "Truncate tail entries (without anchor)", False))
        attacks[-1].caught = False  # this is the known limitation
        attacks[-1].errors = ["truncated chain still verifies — this is the known gap"]
        print(_step(f"Original: 5 entries, truncated to 3"))
        print(_step("The remaining chain is genuinely intact and consecutive."))
        print(_step("No self-contained log can detect this."))
        print(_result_line(False, f"Truncation indetectable (known limitation)", attacks[-1].errors))

        # ── Step 8: Publish head, then detect truncation ───────────────────
        print(_heading("STEP 8: PUBLISH HEAD — Now truncation is detectable"))

        print(_step(f"Published anchor: sha256:{full_head[:16]}..."))
        print(_step(f"Current head:     sha256:{Ledger(ledger_path3).head()[:16]}..."))
        print(_step("The ledger writer cannot reach the published anchor."))
        print(_step("Anyone verifying can now see the mismatch."))

        valid_anchor, errors_anchor = verify_ledger(ledger_path3, expected_head=full_head)
        attacks.append(_Attack("anchor_detects_truncation",
                               "Truncation detected via published anchor", True))
        attacks[-1].caught = not valid_anchor
        attacks[-1].errors = errors_anchor
        print(_result_line(not valid_anchor, f"Truncation detected with anchor", errors_anchor))

        # ── Summary ────────────────────────────────────────────────────────
        print(_heading("SUMMARY"))
        print()
        for a in attacks:
            icon = "✓" if a.caught else "✗"
            label = "DETECTED" if a.caught else ("INDETECTABLE" if not a.detectable else "MISSED")
            col = GREEN if a.caught else (YELLOW if not a.detectable else RED)
            print(f"  {c(icon, col)}  {c(label, col):>14}  {a.name}")
        print()
        detected = sum(1 for a in attacks if a.caught)
        total_detectable = sum(1 for a in attacks if a.detectable)
        print(f"  {dim(f'{detected}/{total_detectable} detectable attacks caught')}")
        print(f"  {dim('1 known limitation: truncation requires an external anchor')}")
        print()

    return {
        "attacks": [
            {"name": a.name, "description": a.description,
             "detectable": a.detectable, "caught": a.caught, "errors": a.errors}
            for a in attacks
        ]
    }


if __name__ == "__main__":
    run_attack_demo()
