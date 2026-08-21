from __future__ import annotations

import unittest

from trustdocs.pipeline import Extraction, FieldValue
from trustdocs.validation import (
    ConfidenceWarningRule,
    LineItemsConsistentRule,
    NonNegativeNumberRule,
    RequiredFieldsRule,
    validate,
)


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


class LineItemsConsistentRuleTests(unittest.TestCase):
    rule = LineItemsConsistentRule("line_items", "total_amount", "line-items-reconcile")

    def _extraction(self, items, total):
        return Extraction({ "line_items": FieldValue(items, 0.9, {"s": "t"}),
                          "total_amount": FieldValue(total, 0.9, {"s": "t"}) }, 0.9)

    def test_reconciled_single_row_passes(self):
        items = [{"description": "A", "quantity": 2, "unit_price": 10.0, "total": 20.0}]
        self.assertEqual(self.rule.check(self._extraction(items, 20.0)).status, "PASS")

    def test_reconciled_multi_row_passes(self):
        items = [
            {"description": "A", "quantity": 2, "unit_price": 10.0, "total": 20.0},
            {"description": "B", "quantity": 3, "unit_price": 15.0, "total": 45.0},
        ]
        self.assertEqual(self.rule.check(self._extraction(items, 65.0)).status, "PASS")

    def test_mismatch_fail(self):
        items = [{"description": "A", "quantity": 2, "unit_price": 10.0, "total": 20.0}]
        self.assertEqual(self.rule.check(self._extraction(items, 99.0)).status, "FAIL")

    def test_tolerance_allows_penny_rounding(self):
        items = [{"description": "A", "quantity": 3, "unit_price": 0.33, "total": 0.99}]
        # 3 * 0.33 = 0.99 — exact match
        self.assertEqual(self.rule.check(self._extraction(items, 0.99)).status, "PASS")

    def test_non_dict_row_fails(self):
        items = ["not-a-dict", 42, None]
        self.assertEqual(self.rule.check(self._extraction(items, 0.0)).status, "FAIL")

    def test_missing_quantity_fails(self):
        items = [{"description": "A", "unit_price": 10.0}]
        self.assertEqual(self.rule.check(self._extraction(items, 10.0)).status, "FAIL")

    def test_missing_unit_price_fails(self):
        items = [{"description": "A", "quantity": 2}]
        self.assertEqual(self.rule.check(self._extraction(items, 20.0)).status, "FAIL")

    def test_bool_quantity_rejected_as_non_numeric(self):
        # isinstance(True, int) == True in Python — the rule must exclude bool explicitly
        items = [{"description": "A", "quantity": True, "unit_price": 10.0}]
        self.assertEqual(self.rule.check(self._extraction(items, 10.0)).status, "FAIL")

    def test_bool_unit_price_rejected(self):
        items = [{"description": "A", "quantity": 2, "unit_price": False}]
        self.assertEqual(self.rule.check(self._extraction(items, 20.0)).status, "FAIL")

    def test_non_list_items_fails(self):
        ext = Extraction({"line_items": FieldValue("not-a-list", 0.9, {}),
                          "total_amount": FieldValue(10.0, 0.9, {})}, 0.9)
        self.assertEqual(self.rule.check(ext).status, "FAIL")

    def test_non_numeric_total_fails(self):
        ext = Extraction({"line_items": FieldValue([], 0.9, {}),
                          "total_amount": FieldValue("abc", 0.9, {})}, 0.9)
        self.assertEqual(self.rule.check(ext).status, "FAIL")

    def test_bool_total_rejected(self):
        ext = Extraction({"line_items": FieldValue([], 0.9, {}),
                          "total_amount": FieldValue(True, 0.9, {})}, 0.9)
        self.assertEqual(self.rule.check(ext).status, "FAIL")

    def test_missing_fields_warns(self):
        ext = Extraction({}, 0.9)
        self.assertEqual(self.rule.check(ext).status, "WARNING")

    def test_empty_list_reconciles_with_zero(self):
        ext = Extraction({"line_items": FieldValue([], 0.9, {}),
                          "total_amount": FieldValue(0.0, 0.9, {})}, 0.9)
        self.assertEqual(self.rule.check(ext).status, "PASS")


if __name__ == "__main__":
    unittest.main()
