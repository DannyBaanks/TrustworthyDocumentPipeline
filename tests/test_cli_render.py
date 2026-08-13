from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout

from trustdocs import cli
from trustdocs.render import render_pretty


class RenderPrettyTests(unittest.TestCase):
    def test_never_prints_extracted_field_values(self) -> None:
        outcome = {
            "status": "APPROVED_BY_HUMAN", "document_sha256": "a" * 64,
            "field_count": 1, "reviewed": True, "evidence_sha256": "b" * 64,
            "execution_id": "exec-1", "evidence_path": None,
            "validation": [{"rule_id": "r1", "status": "PASS", "message": "ok"}],
        }
        block = render_pretty(outcome, color_enabled=False)
        self.assertIn("APPROVED_BY_HUMAN", block)
        self.assertIn("r1", block)
        # The whole point of this CLI: never leak extracted values.
        self.assertNotIn("invoice", block.lower())
        self.assertNotIn("total_amount", block)

    def test_status_and_validation_icons_present_without_color(self) -> None:
        outcome = {
            "status": "REJECTED", "document_sha256": "a" * 64, "field_count": 0,
            "reviewed": True, "evidence_sha256": "b" * 64, "execution_id": "exec-2",
            "evidence_path": None,
            "validation": [{"rule_id": "r1", "status": "FAIL", "message": "bad"}],
        }
        block = render_pretty(outcome, color_enabled=False)
        self.assertIn("REJECTED", block)
        self.assertIn("r1", block)
        self.assertIn("bad", block)
        # No ANSI escape codes leak through when color is disabled.
        self.assertNotIn("\033[", block)


class CliOutputModeTests(unittest.TestCase):
    def test_demo_defaults_to_pretty_output(self) -> None:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            cli.main(["--demo"])
        output = buffer.getvalue()
        self.assertIn("Trustworthy Document Pipeline", output)
        with self.assertRaises(json.JSONDecodeError):
            json.loads(output)

    def test_json_flag_produces_parseable_json(self) -> None:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            cli.main(["--demo", "--json"])
        payload = json.loads(buffer.getvalue())
        self.assertEqual(payload["status"], "AUTO_APPROVED")
        self.assertNotIn("kind", payload)
        self.assertNotIn("_json_requested", payload)

    def test_demo_warning_pretty_output_shows_the_triggered_rule(self) -> None:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            cli.main(["--demo-warning"])
        output = buffer.getvalue()
        self.assertIn("review-low-total-confidence", output)
        self.assertIn("low confidence", output)


if __name__ == "__main__":
    unittest.main()
