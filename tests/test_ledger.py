"""Tests for the append-only decision ledger.

A single evidence record proves its own integrity. It cannot prove anything
about the set: delete one file and every remaining record still verifies
cleanly. The ledger closes that gap by chaining entries, so the question an
auditor actually asks -- "show me that nothing is missing" -- has an answer.

The last test in this file documents what the chain still cannot do, and it is
deliberately named as a limitation rather than skipped.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from trustdocs.ledger import Ledger, LedgerEntry, verify_ledger


class LedgerTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.path = Path(self._tmp.name) / "ledger.jsonl"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _append(self, ledger: Ledger, n: int) -> None:
        for i in range(n):
            ledger.append(
                execution_id=f"exec-{i}",
                record_sha256=f"{i:064x}",
                document_sha256=f"{i + 100:064x}",
                decision="AUTO_APPROVED",
            )

    def _rows(self) -> list[dict]:
        return [json.loads(line) for line in
                self.path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def _rewrite(self, rows: list[dict]) -> None:
        self.path.write_text(
            "".join(json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n" for r in rows),
            encoding="utf-8")

    # -- writing ------------------------------------------------------------

    def test_first_entry_has_no_predecessor(self):
        ledger = Ledger(self.path)
        entry = ledger.append(execution_id="e", record_sha256="a" * 64,
                              document_sha256="b" * 64, decision="AUTO_APPROVED")
        self.assertEqual(entry.sequence, 0)
        self.assertIsNone(entry.prev_entry_sha256)

    def test_each_entry_points_at_the_one_before_it(self):
        ledger = Ledger(self.path)
        self._append(ledger, 3)
        rows = self._rows()
        self.assertEqual([r["sequence"] for r in rows], [0, 1, 2])
        self.assertEqual(rows[1]["prev_entry_sha256"], rows[0]["entry_sha256"])
        self.assertEqual(rows[2]["prev_entry_sha256"], rows[1]["entry_sha256"])

    def test_appending_reopens_an_existing_ledger(self):
        self._append(Ledger(self.path), 2)
        entry = Ledger(self.path).append(execution_id="e2", record_sha256="c" * 64,
                                         document_sha256="d" * 64, decision="REJECTED")
        self.assertEqual(entry.sequence, 2)
        self.assertEqual(entry.prev_entry_sha256, self._rows()[1]["entry_sha256"])

    # -- verification -------------------------------------------------------

    def test_an_intact_ledger_verifies(self):
        self._append(Ledger(self.path), 5)
        ok, errors = verify_ledger(self.path)
        self.assertTrue(ok, errors)
        self.assertEqual(errors, [])

    def test_an_empty_ledger_is_valid(self):
        self.path.write_text("", encoding="utf-8")
        ok, errors = verify_ledger(self.path)
        self.assertTrue(ok, errors)

    def test_a_modified_entry_is_caught_and_located(self):
        self._append(Ledger(self.path), 4)
        rows = self._rows()
        rows[2]["decision"] = "AUTO_APPROVED_BUT_ACTUALLY_NOT"
        self._rewrite(rows)

        ok, errors = verify_ledger(self.path)
        self.assertFalse(ok)
        self.assertTrue(any("entry 2" in e for e in errors), errors)

    def test_a_deleted_entry_is_caught(self):
        """The case a per-file evidence scheme cannot detect at all."""
        self._append(Ledger(self.path), 4)
        rows = self._rows()
        del rows[1]
        self._rewrite(rows)

        ok, errors = verify_ledger(self.path)
        self.assertFalse(ok)
        self.assertTrue(any("missing" in e.lower() or "sequence" in e.lower() for e in errors),
                        errors)

    def test_an_inserted_entry_is_caught(self):
        self._append(Ledger(self.path), 3)
        rows = self._rows()
        forged = dict(rows[1])
        forged["execution_id"] = "forged"
        rows.insert(2, forged)
        self._rewrite(rows)

        ok, errors = verify_ledger(self.path)
        self.assertFalse(ok)

    def test_reordering_is_caught(self):
        self._append(Ledger(self.path), 4)
        rows = self._rows()
        rows[1], rows[2] = rows[2], rows[1]
        self._rewrite(rows)

        ok, errors = verify_ledger(self.path)
        self.assertFalse(ok)

    def test_verification_reports_every_break_not_only_the_first(self):
        self._append(Ledger(self.path), 6)
        rows = self._rows()
        rows[1]["decision"] = "X"
        rows[4]["decision"] = "Y"
        self._rewrite(rows)

        ok, errors = verify_ledger(self.path)
        self.assertFalse(ok)
        self.assertGreaterEqual(len(errors), 2, errors)

    # -- what the chain cannot do -------------------------------------------

    def test_LIMITATION_truncating_the_tail_is_not_detectable(self):
        """Cutting entries off the end leaves a perfectly valid shorter chain.

        No self-contained log can detect this: the remaining entries are
        genuinely intact and genuinely consecutive. Detecting it requires an
        anchor kept somewhere the writer cannot reach -- publishing the head
        hash externally, which `Ledger.head()` exists to support.

        This test asserts the weakness so it cannot be quietly forgotten, and
        so the README claim stays honest.
        """
        self._append(Ledger(self.path), 5)
        rows = self._rows()
        self._rewrite(rows[:3])

        ok, errors = verify_ledger(self.path)
        self.assertTrue(ok, "a truncated chain still verifies -- this is the known gap")

        # The anchor is what closes it.
        self.assertNotEqual(Ledger(self.path).head(), rows[-1]["entry_sha256"])

    def test_head_returns_the_last_entry_hash_as_the_anchor(self):
        self._append(Ledger(self.path), 3)
        self.assertEqual(Ledger(self.path).head(), self._rows()[-1]["entry_sha256"])

    def test_head_of_an_empty_ledger_is_none(self):
        self.assertIsNone(Ledger(self.path).head())


class LedgerQueryTests(unittest.TestCase):
    """An auditor does not read a JSONL file; they ask questions of it."""

    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.path = Path(self._tmp.name) / "ledger.jsonl"
        ledger = Ledger(self.path)
        for i, decision in enumerate(
                ["AUTO_APPROVED", "REJECTED", "APPROVED_BY_HUMAN", "AUTO_APPROVED"]):
            ledger.append(execution_id=f"e{i}", record_sha256=f"{i:064x}",
                          document_sha256=f"{i + 50:064x}", decision=decision)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_entries_can_be_filtered_by_decision(self):
        auto = Ledger(self.path).entries(decision="AUTO_APPROVED")
        self.assertEqual(len(auto), 2)
        self.assertTrue(all(e.decision == "AUTO_APPROVED" for e in auto))

    def test_a_document_can_be_traced_to_its_decision(self):
        found = Ledger(self.path).find_document(f"{51:064x}")
        self.assertIsNotNone(found)
        self.assertEqual(found.decision, "REJECTED")

    def test_an_unknown_document_returns_nothing_rather_than_guessing(self):
        self.assertIsNone(Ledger(self.path).find_document("f" * 64))

    def test_summary_counts_decisions(self):
        summary = Ledger(self.path).summary()
        self.assertEqual(summary["total"], 4)
        self.assertEqual(summary["by_decision"]["AUTO_APPROVED"], 2)
        self.assertEqual(summary["by_decision"]["REJECTED"], 1)


if __name__ == "__main__":
    unittest.main()
