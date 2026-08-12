"""Minimal validation rules for normalized document fields."""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, Literal

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

    def check(self, extraction: "Extraction") -> ValidationFinding:
        ...


@dataclass(frozen=True, slots=True)
class RequiredFieldsRule:
    fields: tuple[str, ...]
    rule_id: str = "required-fields"

    def check(self, extraction: "Extraction") -> ValidationFinding:
        missing = [name for name in self.fields if name not in extraction.fields]
        if missing:
            return ValidationFinding(self.rule_id, "FAIL", f"missing fields: {missing}")
        return ValidationFinding(self.rule_id, "PASS", "all required fields present")


@dataclass(frozen=True, slots=True)
class NonNegativeNumberRule:
    field: str
    rule_id: str

    def check(self, extraction: "Extraction") -> ValidationFinding:
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


def validate(extraction: "Extraction", rules: tuple[ValidationRule, ...]) -> tuple[ValidationFinding, ...]:
    return tuple(rule.check(extraction) for rule in rules)
