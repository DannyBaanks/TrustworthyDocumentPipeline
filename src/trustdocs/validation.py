"""Minimal validation rules for normalized document fields."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol

if TYPE_CHECKING:
    from .pipeline import Extraction

ValidationStatus = Literal["PASS", "WARNING", "FAIL"]


@dataclass(frozen=True, slots=True)
class ValidationFinding:
    rule_id: str
    status: ValidationStatus
    message: str


class ValidationRule(Protocol):
    rule_id: str

    def check(self, extraction: Extraction) -> ValidationFinding:
        ...


@dataclass(frozen=True, slots=True)
class RequiredFieldsRule:
    fields: tuple[str, ...]
    rule_id: str = "required-fields"

    def check(self, extraction: Extraction) -> ValidationFinding:
        missing = [name for name in self.fields if name not in extraction.fields]
        if missing:
            return ValidationFinding(self.rule_id, "FAIL", f"missing fields: {missing}")
        return ValidationFinding(self.rule_id, "PASS", "all required fields present")


@dataclass(frozen=True, slots=True)
class NonNegativeNumberRule:
    field: str
    rule_id: str

    def check(self, extraction: Extraction) -> ValidationFinding:
        field = extraction.fields.get(self.field)
        if field is None:
            return ValidationFinding(self.rule_id, "WARNING", f"field unavailable: {self.field}")
        if not isinstance(field.value, (int, float)) or isinstance(field.value, bool):
            return ValidationFinding(self.rule_id, "FAIL", f"field is not numeric: {self.field}")
        if field.value < 0:
            return ValidationFinding(self.rule_id, "FAIL", f"field is negative: {self.field}")
        return ValidationFinding(self.rule_id, "PASS", f"field is non-negative: {self.field}")


@dataclass(frozen=True, slots=True)
class ConfidenceWarningRule:
    field: str
    threshold: float
    rule_id: str

    def check(self, extraction: Extraction) -> ValidationFinding:
        field = extraction.fields.get(self.field)
        if field is None or field.confidence is None:
            return ValidationFinding(self.rule_id, "WARNING", f"confidence unavailable: {self.field}")
        if field.confidence < self.threshold:
            return ValidationFinding(self.rule_id, "WARNING", f"low confidence: {self.field}")
        return ValidationFinding(self.rule_id, "PASS", f"confidence acceptable: {self.field}")


@dataclass(frozen=True, slots=True)
class LineItemsConsistentRule:
    items_field: str
    total_field: str
    rule_id: str

    def check(self, extraction: Extraction) -> ValidationFinding:
        items = extraction.fields.get(self.items_field)
        total = extraction.fields.get(self.total_field)
        if items is None or total is None:
            return ValidationFinding(self.rule_id, "WARNING", f"fields unavailable: {self.items_field}, {self.total_field}")
        if not isinstance(items.value, list):
            return ValidationFinding(self.rule_id, "FAIL", f"{self.items_field} is not a list")
        if not isinstance(total.value, (int, float)) or isinstance(total.value, bool):
            return ValidationFinding(self.rule_id, "FAIL", f"{self.total_field} is not numeric")
        computed = 0.0
        for row in items.value:
            if not isinstance(row, dict):
                return ValidationFinding(self.rule_id, "FAIL", "line item is not an object")
            quantity = row.get("quantity")
            unit_price = row.get("unit_price")

            def _is_numeric(v) -> bool:
                return isinstance(v, (int, float)) and not isinstance(v, bool)
            if not _is_numeric(quantity) or not _is_numeric(unit_price):
                return ValidationFinding(self.rule_id, "FAIL", "line item has non-numeric quantity/unit_price")
            computed += quantity * unit_price
        if abs(computed - float(total.value)) > 0.005:
            return ValidationFinding(self.rule_id, "FAIL", "line item totals do not reconcile with total")
        return ValidationFinding(self.rule_id, "PASS", "line items reconcile with total")


def validate(extraction: Extraction, rules: tuple[ValidationRule, ...]) -> tuple[ValidationFinding, ...]:
    return tuple(rule.check(extraction) for rule in rules)
