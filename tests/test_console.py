"""Tests for the auditor console.

The console is a single self-contained HTML file generated from a ledger. It
matters that it is *independent*: it embeds the ledger data and recomputes every
hash in the browser, so an auditor is not taking the word of the tool that
produced the page.

Two properties are load-bearing and both are tested here:

- it never contains extracted field values, because the whole point of the
  evidence design is that it proves what was decided without republishing the
  contents of the document;
- it needs no network, so it can be opened from a USB stick in an audit room.
"""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from trustdocs.console import canonical_json, render_console
from trustdocs.ledger import Ledger


class ConsoleRenderTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = TemporaryDirectory()
        self.path = Path(self._tmp.name) / "ledger.jsonl"
        ledger = Ledger(self.path)
        for i, decision in enumerate(
                ["AUTO_APPROVED", "REJECTED", "APPROVED_BY_HUMAN"]):
            ledger.append(execution_id=f"exec-{i}", record_sha256=f"{i:064x}",
                          document_sha256=f"{i + 90:064x}", decision=decision)
        self.html = render_console(self.path)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_every_entry_is_embedded(self):
        for i in range(3):
            self.assertIn(f"exec-{i}", self.html)

    def test_the_head_is_shown_as_the_anchor_to_publish(self):
        self.assertIn(Ledger(self.path).head(), self.html)

    def test_it_makes_no_network_requests(self):
        """An audit room may have no internet, and a page that phones home is
        not evidence of anything."""
        for forbidden in ("http://", "https://", "fetch(", "XMLHttpRequest",
                          "<script src=", "<link rel=\"stylesheet\" href="):
            self.assertNotIn(forbidden, self.html)

    def test_it_carries_its_own_sha256_implementation(self):
        """Recomputed in the browser rather than trusted from the generator.

        crypto.subtle is unavailable over file://, which is exactly how an
        auditor will open this, so the digest is implemented in plain JS.
        """
        self.assertIn("function sha256", self.html)
        self.assertNotIn("crypto.subtle", self.html)

    def test_no_extracted_document_values_are_present(self):
        """The ledger holds hashes and decisions, never field values. If that
        ever changes, this test fails before the leak ships."""
        embedded = re.search(r"const LEDGER = (\[.*?\]);", self.html, re.S)
        self.assertIsNotNone(embedded)
        rows = json.loads(embedded.group(1))
        allowed = {"schema", "sequence", "prev_entry_sha256", "recorded_at",
                   "execution_id", "record_sha256", "document_sha256",
                   "decision", "entry_sha256"}
        for row in rows:
            self.assertEqual(set(row) - allowed, set(), f"unexpected field in {row}")

    def test_decisions_are_summarised(self):
        self.assertIn("AUTO_APPROVED", self.html)
        self.assertIn("REJECTED", self.html)

    def test_an_empty_ledger_renders_a_page_rather_than_failing(self):
        empty = Path(self._tmp.name) / "empty.jsonl"
        empty.write_text("", encoding="utf-8")
        html = render_console(empty)
        self.assertIn("const LEDGER = [];", html)
        self.assertIn("(empty ledger)", html)

    def test_both_themes_are_defined(self):
        self.assertIn("prefers-color-scheme", self.html)

    def test_hostile_ledger_content_cannot_break_out_of_the_script_block(self):
        """Ledger values arrive from whatever ran the pipeline: treat as data.

        The defence is two-layered and this asserts both, rather than asserting
        that a scary-looking string is absent -- it is present, inert, inside a
        JS string literal, and that is fine.

        1. `</` is escaped, so no value can terminate the <script> element.
        2. Rows are painted with textContent, which never parses HTML.
        """
        hostile = Path(self._tmp.name) / "hostile.jsonl"
        Ledger(hostile).append(execution_id="</script><img src=x onerror=alert(1)>",
                               record_sha256="a" * 64, document_sha256="b" * 64,
                               decision="AUTO_APPROVED")
        html = render_console(hostile)

        script_body = html.split("<script>", 1)[1].split("</script>", 1)[0]
        self.assertIn("<\\/script>", script_body)
        self.assertNotIn("</script>", script_body)

        self.assertIn("td.textContent = text", html)
        self.assertNotIn("innerHTML = '<", html)

    def test_rows_are_never_built_by_string_concatenation_into_innerHTML(self):
        """The one pattern that would reintroduce injection."""
        for pattern in ("innerHTML +=", "innerHTML = '<tr", 'innerHTML = "<tr'):
            self.assertNotIn(pattern, self.html)


class CanonicalJsonTests(unittest.TestCase):
    """The browser must hash bytes identical to the ones Python hashed."""

    def test_keys_are_sorted_and_separators_tight(self):
        self.assertEqual(canonical_json({"b": 1, "a": 2}), '{"a":2,"b":1}')

    def test_nulls_survive(self):
        self.assertEqual(canonical_json({"a": None}), '{"a":null}')

    def test_it_matches_the_digest_helper_used_by_the_ledger(self):
        from trustdocs.evidence import _digest
        import hashlib

        body = {"sequence": 0, "prev_entry_sha256": None, "recorded_at": "2026-01-01",
                "execution_id": "e", "record_sha256": "a", "document_sha256": "b",
                "decision": "AUTO_APPROVED"}
        expected = _digest(body)
        actual = hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest()
        self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()


class BrowserAgreesWithPythonTests(unittest.TestCase):
    """Run the page's own JavaScript and check it agrees with Python.

    This is the load-bearing assumption of the whole console: the browser
    recomputes hashes over bytes canonicalised exactly the way Python
    canonicalised them. The contract is narrow -- it holds because every value
    in an entry body is a string, an integer or null -- and it would break
    silently the day someone adds a float, since Python writes 0.0 where
    JavaScript writes 0.

    Skipped when Node is unavailable, because a missing tool is not a failure;
    it just means this guarantee went unchecked on this machine.
    """

    def setUp(self) -> None:
        import shutil
        if not shutil.which("node"):
            self.skipTest("node not available; cross-language hash check skipped")
        self._tmp = TemporaryDirectory()
        self.path = Path(self._tmp.name) / "ledger.jsonl"

    def tearDown(self) -> None:
        if hasattr(self, "_tmp"):
            self._tmp.cleanup()

    def _run_node(self, rows) -> dict:
        import subprocess
        from trustdocs.console import _SHA256_JS, _VERIFY_JS

        script = Path(self._tmp.name) / "check.js"
        script.write_text(
            _SHA256_JS + _VERIFY_JS
            + f"const LEDGER = {json.dumps(rows)};\n"
            + "const r = verifyChain(LEDGER);\n"
            + "console.log(JSON.stringify({ok: r.ok, problems: r.problems, head: r.head}));\n",
            encoding="utf-8")
        out = subprocess.run(["node", str(script)], capture_output=True, text=True,
                             timeout=60, encoding="utf-8")
        self.assertEqual(out.returncode, 0, out.stderr)
        return json.loads(out.stdout.strip().splitlines()[-1])

    def test_javascript_confirms_a_chain_python_wrote(self):
        ledger = Ledger(self.path)
        for i in range(4):
            ledger.append(execution_id=f"exec-{i}", record_sha256=f"{i:064x}",
                          document_sha256=f"{i + 7:064x}", decision="AUTO_APPROVED")
        rows = [e.to_dict() for e in ledger.entries()]

        verdict = self._run_node(rows)
        self.assertTrue(verdict["ok"], verdict["problems"])
        self.assertEqual(verdict["head"], Ledger(self.path).head())

    def test_javascript_catches_tampering_python_would_catch(self):
        ledger = Ledger(self.path)
        for i in range(3):
            ledger.append(execution_id=f"exec-{i}", record_sha256=f"{i:064x}",
                          document_sha256=f"{i + 7:064x}", decision="AUTO_APPROVED")
        rows = [e.to_dict() for e in ledger.entries()]
        rows[1]["decision"] = "REJECTED"

        verdict = self._run_node(rows)
        self.assertFalse(verdict["ok"])
        self.assertTrue(any("entry 1" in p for p in verdict["problems"]), verdict["problems"])

    def test_javascript_handles_unicode_the_same_way(self):
        """utf8() in the page exists for exactly this; without it any non-ASCII
        value would hash differently in the two languages."""
        ledger = Ledger(self.path)
        ledger.append(execution_id="factura-año-Ñ-日本", record_sha256="a" * 64,
                      document_sha256="b" * 64, decision="APPROVED_BY_HUMAN")
        rows = [e.to_dict() for e in ledger.entries()]

        verdict = self._run_node(rows)
        self.assertTrue(verdict["ok"], verdict["problems"])
