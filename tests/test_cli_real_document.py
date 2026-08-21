from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from trustdocs.cli import run


class RealDocumentRejectionTests(unittest.TestCase):
    def test_missing_file_reports_error(self) -> None:
        # _run_real_document only runs for real paths; use a non-existent one
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "does-not-exist.pdf"
            with self.assertRaises(SystemExit):
                run([str(missing), "--json"])

    def test_unsupported_suffix_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "file.txt"
            path.write_text("hello", encoding="utf-8")
            with self.assertRaises(SystemExit):
                run([str(path), "--json"])

    def test_oversize_file_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "big.pdf"
            path.write_bytes(b"x" * (10_000_001))
            with self.assertRaises(SystemExit):
                run([str(path), "--json"])


if __name__ == "__main__":
    unittest.main()
