"""Tests for the ledger commands.

The ledger only exists for a user if the CLI exposes it. These tests drive it
the way the demo video will: run decisions, then ask the ledger questions about
them.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from trustdocs.cli import run


class LedgerCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.ledger = Path(self._tmp.name) / "ledger.jsonl"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _record_three(self) -> None:
        for flag in ("--demo", "--demo-warning", "--demo-inconsistent"):
            run([flag, "--ledger", str(self.ledger)])

    # -- writing ------------------------------------------------------------

    def test_a_demo_run_appends_to_the_ledger_when_one_is_given(self):
        run(["--demo", "--ledger", str(self.ledger)])
        lines = self.ledger.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(lines), 1)
        entry = json.loads(lines[0])
        self.assertEqual(entry["decision"], "AUTO_APPROVED")
        self.assertEqual(entry["sequence"], 0)

    def test_no_ledger_is_written_when_none_is_requested(self):
        outcome = run(["--demo"])
        self.assertIsNone(outcome.get("ledger_entry"))
        self.assertFalse(self.ledger.exists())

    def test_successive_runs_chain(self):
        self._record_three()
        rows = [json.loads(l) for l in
                self.ledger.read_text(encoding="utf-8").strip().splitlines()]
        self.assertEqual([r["sequence"] for r in rows], [0, 1, 2])
        self.assertEqual(rows[1]["prev_entry_sha256"], rows[0]["entry_sha256"])

    def test_the_run_reports_where_it_was_recorded(self):
        outcome = run(["--demo", "--ledger", str(self.ledger)])
        self.assertEqual(outcome["ledger_entry"]["sequence"], 0)
        self.assertIn("entry_sha256", outcome["ledger_entry"])

    # -- querying -----------------------------------------------------------

    def test_verify_reports_an_intact_chain(self):
        self._record_three()
        outcome = run(["ledger", "verify", "--ledger", str(self.ledger)])
        self.assertEqual(outcome["status"], "VALID")
        self.assertEqual(outcome["entries"], 3)

    def test_verify_detects_tampering_and_says_where(self):
        self._record_three()
        rows = [json.loads(l) for l in
                self.ledger.read_text(encoding="utf-8").strip().splitlines()]
        rows[1]["decision"] = "AUTO_APPROVED"
        self.ledger.write_text(
            "".join(json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n"
                    for r in rows), encoding="utf-8")

        outcome = run(["ledger", "verify", "--ledger", str(self.ledger)])
        self.assertEqual(outcome["status"], "INVALID")
        self.assertTrue(any("entry 1" in e for e in outcome["errors"]), outcome["errors"])

    def test_verify_against_a_published_anchor_catches_truncation(self):
        """The chain alone cannot see a cut tail; the anchor can."""
        self._record_three()
        head = run(["ledger", "head", "--ledger", str(self.ledger)])["head"]

        rows = self.ledger.read_text(encoding="utf-8").strip().splitlines()
        self.ledger.write_text("\n".join(rows[:2]) + "\n", encoding="utf-8")

        without = run(["ledger", "verify", "--ledger", str(self.ledger)])
        self.assertEqual(without["status"], "VALID", "truncation is invisible without an anchor")

        with_anchor = run(["ledger", "verify", "--ledger", str(self.ledger),
                           "--expect-head", head])
        self.assertEqual(with_anchor["status"], "INVALID")
        self.assertTrue(any("head" in e.lower() for e in with_anchor["errors"]))

    def test_head_prints_the_anchor(self):
        self._record_three()
        outcome = run(["ledger", "head", "--ledger", str(self.ledger)])
        self.assertEqual(len(outcome["head"]), 64)

    def test_head_of_an_empty_ledger_is_reported_not_crashed(self):
        self.ledger.write_text("", encoding="utf-8")
        outcome = run(["ledger", "head", "--ledger", str(self.ledger)])
        self.assertIsNone(outcome["head"])

    def test_summary_counts_by_decision(self):
        self._record_three()
        outcome = run(["ledger", "summary", "--ledger", str(self.ledger)])
        self.assertEqual(outcome["summary"]["total"], 3)
        self.assertIn("AUTO_APPROVED", outcome["summary"]["by_decision"])

    def test_trace_finds_the_decision_for_a_document(self):
        run(["--demo", "--ledger", str(self.ledger)])
        doc = json.loads(self.ledger.read_text(encoding="utf-8").strip())["document_sha256"]

        outcome = run(["ledger", "trace", doc, "--ledger", str(self.ledger)])
        self.assertEqual(outcome["found"], True)
        self.assertEqual(outcome["entry"]["decision"], "AUTO_APPROVED")

    def test_trace_of_an_unknown_document_says_so(self):
        self._record_three()
        outcome = run(["ledger", "trace", "f" * 64, "--ledger", str(self.ledger)])
        self.assertEqual(outcome["found"], False)

    def test_verify_of_a_missing_ledger_fails_cleanly(self):
        outcome = run(["ledger", "verify", "--ledger",
                       str(Path(self._tmp.name) / "nope.jsonl")])
        self.assertEqual(outcome["status"], "INVALID")
        self.assertTrue(outcome["errors"])



class LedgerMainTests(unittest.TestCase):
    """Drive main(), not run().

    The first version of the ledger commands passed every run()-level test and
    still crashed for a real user: main() routed the ledger outcome through the
    process renderer, which reads a document hash the ledger result does not
    have. Testing the function under the entry point is not the same as testing
    the entry point.
    """

    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.ledger = Path(self._tmp.name) / "ledger.jsonl"
        for flag in ("--demo", "--demo-warning", "--demo-inconsistent"):
            run([flag, "--ledger", str(self.ledger)])

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _main(self, argv):
        from contextlib import redirect_stdout
        from io import StringIO

        from trustdocs.cli import main
        buffer = StringIO()
        with redirect_stdout(buffer):
            code = main(argv)
        return code, buffer.getvalue()

    def test_every_ledger_action_renders_without_crashing(self):
        doc = json.loads(
            self.ledger.read_text(encoding="utf-8").splitlines()[0])["document_sha256"]
        for argv in (["ledger", "verify"], ["ledger", "head"], ["ledger", "summary"],
                     ["ledger", "trace", doc]):
            with self.subTest(argv=argv):
                code, output = self._main(argv + ["--ledger", str(self.ledger)])
                self.assertEqual(code, 0, output)
                self.assertTrue(output.strip())

    def test_a_broken_chain_exits_nonzero(self):
        rows = self.ledger.read_text(encoding="utf-8").splitlines()
        self.ledger.write_text("\n".join(rows[:1] + rows[2:]) + "\n", encoding="utf-8")
        code, output = self._main(["ledger", "verify", "--ledger", str(self.ledger)])
        self.assertEqual(code, 1)
        self.assertIn("INVALID", output)

    def test_json_output_is_parseable_for_every_action(self):
        for action in ("verify", "head", "summary"):
            with self.subTest(action=action):
                _, output = self._main(
                    ["ledger", action, "--ledger", str(self.ledger), "--json"])
                json.loads(output)

    def test_a_recorded_run_still_renders_its_own_summary(self):
        code, output = self._main(["--demo", "--ledger", str(self.ledger)])
        self.assertEqual(code, 0)
        self.assertIn("AUTO_APPROVED", output)

if __name__ == "__main__":
    unittest.main()
