from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from trustdocs.evidence import EvidenceNode, EvidenceRecord, read_record, write_record


class EvidenceTests(unittest.TestCase):
    def test_same_execution_inputs_have_same_identity(self) -> None:
        first = EvidenceRecord.create(
            document_hash="doc", operation="extract", configuration={"mode": "structure"},
            extraction_hash="extract", decision_hash="decision", decision="APPROVED",
            field_count=1, reviewed=False,
        )
        second = EvidenceRecord.create(
            document_hash="doc", operation="extract", configuration={"mode": "structure"},
            extraction_hash="extract", decision_hash="decision", decision="APPROVED",
            field_count=1, reviewed=False,
        )
        self.assertEqual(first.execution_id, second.execution_id)

    def test_intact_record_is_valid(self) -> None:
        record = EvidenceRecord.create(
            document_hash="doc", operation="extract", configuration={"mode": "structure"},
            extraction_hash="extract", decision_hash="decision", decision="REVIEW_REQUIRED",
            field_count=2, reviewed=True,
        )
        self.assertEqual(record.verify(), (True, []))

    def test_tampered_record_is_invalid(self) -> None:
        record = EvidenceRecord.create(
            document_hash="doc", operation="extract", configuration={},
            extraction_hash="extract", decision_hash="decision", decision="APPROVED",
            field_count=1, reviewed=False,
        )
        value = record.to_dict()
        value["decision"] = "REJECTED"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evidence.json"
            path.write_text(json.dumps(value), encoding="utf-8")
            loaded = read_record(path)
        valid, errors = loaded.verify()
        self.assertFalse(valid)
        self.assertIn("record hash mismatch", errors)

    def test_record_round_trips(self) -> None:
        record = EvidenceRecord.create(
            document_hash="doc", operation="extract", configuration={},
            extraction_hash="extract", decision_hash="decision", decision="APPROVED",
            field_count=1, reviewed=False,
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evidence.json"
            write_record(path, record)
            self.assertEqual(read_record(path).verify(), (True, []))


class EvidenceNodeTests(unittest.TestCase):
    def test_valid_id_for_intact_node(self) -> None:
        node = EvidenceNode.create("document", "", "abcsha", {"k": 1})
        self.assertTrue(node.valid_id())

    def test_invalid_id_when_tampered(self) -> None:
        node = EvidenceNode.create("document", "", "abcsha", {"k": 1})
        # Construct a node with same id but wrong operation
        tampered = EvidenceNode(
            node.id, "different_op", node.input_hash, node.output_hash,
            node.metadata, node.parent_ids,
        )
        self.assertFalse(tampered.valid_id())


class EvidenceVerifyBranchesTests(unittest.TestCase):
    def _record(self, reviewed=True):
        return EvidenceRecord.create(
            document_hash="doc", operation="extract", configuration={"m": "s"},
            extraction_hash="ext", decision_hash="dec", decision="APPROVED",
            field_count=1, reviewed=reviewed,
        )

    def test_missing_parent_reported(self) -> None:
        record = self._record()
        # Forged: a node referencing a parent id that doesn't exist
        orphan = EvidenceNode.create(
            "ghost", "nonexistent-parent", "ghosthash", {"x": 1},
            parent_ids=("not-a-real-parent",),
        )
        nodes = record.nodes + (orphan,)
        forged = EvidenceRecord(record.execution_id, nodes, record.decision, record.record_sha256)
        valid, errors = forged.verify()
        self.assertFalse(valid)
        self.assertIn("missing parent: not-a-real-parent", errors)

    def test_invalid_node_id_reported(self) -> None:
        record = self._record()
        tampered = EvidenceNode(
            "tampered-id-here", record.nodes[0].operation,
            record.nodes[0].input_hash, record.nodes[0].output_hash,
            record.nodes[0].metadata, record.nodes[0].parent_ids,
        )
        forged = EvidenceRecord(
            record.execution_id, (tampered,) + record.nodes[1:], record.decision, record.record_sha256,
        )
        valid, errors = forged.verify()
        self.assertFalse(valid)
        self.assertTrue(any("invalid node id" in e for e in errors))

    def test_read_record_rejects_wrong_schema(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text(json.dumps({"schema": "wrong", "nodes": [], "decision": "x", "execution_id": "e", "record_sha256": "r"}), encoding="utf-8")
            with self.assertRaises(ValueError) as ctx:
                read_record(path)
            self.assertIn("schema", str(ctx.exception))

    def test_read_record_rejects_missing_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text(json.dumps({"schema": "trustdocs.evidence/1"}), encoding="utf-8")
            with self.assertRaises(KeyError):
                read_record(path)

    def test_reviewed_record_has_four_nodes(self) -> None:
        record = self._record(reviewed=True)
        self.assertEqual(len(record.nodes), 4)

    def test_unreviewed_record_has_three_nodes(self) -> None:
        record = self._record(reviewed=False)
        self.assertEqual(len(record.nodes), 3)


if __name__ == "__main__":
    unittest.main()
