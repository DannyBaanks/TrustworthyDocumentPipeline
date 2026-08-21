"""The README must not state a number it does not recompute.

The project's whole argument is that a figure written by hand drifts from the
thing it describes. The README said "126/126 passing" while the suite had grown
to 137 — the exact failure mode the pipeline exists to prevent, in the document
making the claim.

This test collects the real suite and compares. It is deliberately noisy on
failure: the fix is to update the README, not to relax the test.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

README = Path(__file__).resolve().parent.parent / "README.md"
CLAIM = re.compile(r"(\d+)\s*/\s*(\d+)\s+passing")


def collected_test_count() -> int:
    """Count the suite with unittest — the way CI actually runs it.

    This used to shell out to `python -m pytest --collect-only`. CI installs
    only `.[local]` and runs `python -m unittest discover`, so pytest is not
    present there: the subprocess failed, stdout came back empty, and both the
    regex and the fallback returned 0.

    The test that exists so nobody writes a number they have not recomputed was
    therefore comparing against a zero it had invented itself — the exact
    failure mode it is meant to catch. Counting with unittest needs no
    dependency and matches the runner.
    """
    tests_dir = str(README.parent / "tests")
    loader = unittest.TestLoader()
    suite = loader.discover(tests_dir, top_level_dir=tests_dir)
    if loader.errors:
        raise AssertionError(
            "test discovery failed, so any count would be fiction:\n"
            + "\n".join(loader.errors))
    return suite.countTestCases()


class ReadmeClaimsTests(unittest.TestCase):
    def test_the_test_count_in_the_readme_is_the_real_one(self):
        text = README.read_text(encoding="utf-8")
        claim = CLAIM.search(text)
        self.assertIsNotNone(claim, "README no longer states a test count")

        stated = int(claim.group(1))
        actual = collected_test_count()
        self.assertEqual(
            stated, actual,
            f"README claims {stated} tests, the suite has {actual}. "
            f"Update the README — this project does not get to hand-write "
            f"numbers it has not recomputed.")

    def test_both_halves_of_the_claim_agree(self):
        claim = CLAIM.search(README.read_text(encoding="utf-8"))
        self.assertEqual(claim.group(1), claim.group(2),
                         "'N/M passing' with N != M means some are failing")


if __name__ == "__main__":
    unittest.main()
