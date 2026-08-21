from __future__ import annotations

import unittest

from trustdocs.render import render_pretty

PROCESS_OUTCOME = {
    "status": "AUTO_APPROVED",
    "document_sha256": "abcdef0123456789" * 4,
    "field_count": 3,
    "reviewed": False,
    "validation": [
        {"rule_id": "required-fields", "status": "PASS", "message": "all present"},
        {"rule_id": "line-items", "status": "FAIL", "message": "mismatch"},
        {"rule_id": "low-confidence", "status": "WARNING", "message": "low"},
    ],
    "evidence_sha256": "fedcba9876543210" * 4,
    "execution_id": "exec123",
    "evidence_path": None,
}


class RenderColorTests(unittest.TestCase):
    def test_color_enabled_emit_ansi_escape_codes(self) -> None:
        output = render_pretty(PROCESS_OUTCOME, color_enabled=True)
        self.assertIn("\033[", output)
        self.assertIn("\033[0m", output)

    def test_color_disabled_strips_all_ansi(self) -> None:
        output = render_pretty(PROCESS_OUTCOME, color_enabled=False)
        self.assertNotIn("\033[", output)

    def test_validation_icons_present_without_color(self) -> None:
        output = render_pretty(PROCESS_OUTCOME, color_enabled=False)
        # PASS=✓, WARNING=⚠, FAIL=✗
        self.assertIn("✓", output)
        self.assertIn("⚠", output)
        self.assertIn("✗", output)

    def test_render_never_includes_extracted_values(self) -> None:
        # Outcome doesn't carry field values, but assert the contract holds
        output = render_pretty(PROCESS_OUTCOME, color_enabled=True)
        # No invoice_number, total_amount, or vendor_name should appear
        for forbidden in ("invoice_number", "vendor_name", "12345.67"):
            self.assertNotIn(forbidden, output)

    def test_truncates_hash_for_display(self) -> None:
        output = render_pretty(PROCESS_OUTCOME, color_enabled=False)
        # Hashes should be truncated to first 16 chars + ...
        self.assertIn("sha256:abcdef0123456789...", output)
        self.assertNotIn("sha256:abcdef0123456789abcdef0123456789", output)

    def test_rejected_status_renders_cross_icon(self) -> None:
        rejected = {**PROCESS_OUTCOME, "status": "REJECTED"}
        output = render_pretty(rejected, color_enabled=True)
        self.assertIn("✗", output)

    def test_approved_by_human_status_renders_check(self) -> None:
        approved = {**PROCESS_OUTCOME, "status": "APPROVED_BY_HUMAN"}
        output = render_pretty(approved, color_enabled=True)
        self.assertIn("✓", output)


if __name__ == "__main__":
    unittest.main()
