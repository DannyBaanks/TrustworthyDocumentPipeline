from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from trustdocs.evidence import EvidenceRecord, read_record, write_record


class EvidenceTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
