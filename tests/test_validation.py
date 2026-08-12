from __future__ import annotations

import unittest

from trustdocs.pipeline import Extraction, FieldValue
from trustdocs.validation import ConfidenceWarningRule, NonNegativeNumberRule, RequiredFieldsRule, validate


def extraction(**values: object) -> Extraction:
    return Extraction(
        {key: FieldValue(value, 0.9, {"source": "test"}) for key, value in values.items()},
        0.9,
    )


class ValidationTests(unittest.TestCase):
    def test_required_fields_pass(self) -> None:
        result = validate(extraction(invoice_number="A"), (
            RequiredFieldsRule(("invoice_number",)),
        ))
        self.assertEqual(result[0].status, "PASS")

    def test_missing_field_fails(self) -> None:
        result = validate(extraction(), (RequiredFieldsRule(("total_amount",)),))
        self.assertEqual(result[0].status, "FAIL")

    def test_negative_total_fails(self) -> None:
        result = validate(extraction(total_amount=-1), (
            NonNegativeNumberRule("total_amount", "non-negative-total"),
        ))
        self.assertEqual(result[0].status, "FAIL")

    def test_low_confidence_warns(self) -> None:
        result = validate(extraction(total_amount=1), (
            ConfidenceWarningRule("total_amount", 0.95, "low-total-confidence"),
        ))
        self.assertEqual(result[0].status, "WARNING")


if __name__ == "__main__":
    unittest.main()
