"""Deterministic document pipeline with confidence and evidence gates."""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Protocol

from .evidence import EvidenceRecord, _digest
from .validation import FieldConfidencePolicy, ValidationFinding, ValidationRule, validate


@dataclass(frozen=True, slots=True)
class Document:
    content: bytes
    filename: str
    media_type: str

    def __post_init__(self) -> None:
        if not self.content:
            raise ValueError("document must not be empty")
        if not self.filename or "/" in self.filename or "\\" in self.filename:
            raise ValueError("filename must be a basename")
        if not self.media_type:
            raise ValueError("media_type is required")


@dataclass(frozen=True, slots=True)
class FieldValue:
    value: object
    confidence: float | None
    provenance: dict[str, object]


@dataclass(frozen=True, slots=True)
class Extraction:
    fields: dict[str, FieldValue]
    document_confidence: float | None


@dataclass(frozen=True, slots=True)
class ReviewRecord:
    """Evidence that a human reviewed a specific extraction state.

    The review hash enters the evidence chain, creating a verifiable link:
    document hash -> extraction hash -> REVIEW_REQUIRED -> human reviewed
    EXACT extraction hash X -> APPROVED/REJECTED -> review hash -> decision hash.

    This proves not just that a human was involved, but exactly which
    extraction state the human saw when they made their decision.
    """
    review_id: str
    timestamp: str
    reviewer: str
    decision: str
    reason_code: str
    extraction_hash: str

    @classmethod
    def create(cls, *, extraction_hash: str, reviewer: str = "unattributed",
               decision: str, reason_code: str) -> ReviewRecord:
        return cls(
            review_id=uuid.uuid4().hex,
            timestamp=datetime.now(UTC).isoformat(),
            reviewer=reviewer,
            decision=decision,
            reason_code=reason_code,
            extraction_hash=extraction_hash,
        )

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def content_hash(self) -> str:
        return _digest(self.to_dict())


@dataclass(frozen=True, slots=True)
class DecisionRecord:
    status: str
    reason: str
    triggered_rules: tuple[str, ...]
    confidence: float | None
    human_reviewed: bool
    approved: bool
    review: ReviewRecord | None = None


class DocumentService(Protocol):
    name: str

    def extract(self, document: Document) -> Extraction:
        ...


class HumanReviewer(Protocol):
    def review(self, extraction: Extraction) -> bool:
        ...


@dataclass(frozen=True, slots=True)
class PipelineResult:
    status: str
    document_sha256: str
    extraction: Extraction
    reviewed: bool
    approved: bool
    evidence_sha256: str
    evidence: EvidenceRecord
    validation: tuple[ValidationFinding, ...]
    decision: DecisionRecord

    def to_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["extraction"] = asdict(self.extraction)
        return value


class DocumentPipeline:
    def __init__(self, service: DocumentService, reviewer: HumanReviewer,
                 *, confidence_threshold: float = 0.85,
                 rules: tuple[ValidationRule, ...] = ()) -> None:
        if not 0 <= confidence_threshold <= 1:
            raise ValueError("confidence_threshold must be between 0 and 1")
        self.service = service
        self.reviewer = reviewer
        self.confidence_threshold = confidence_threshold
        self.rules = rules

    def run(self, document: Document) -> PipelineResult:
        document_hash = hashlib.sha256(document.content).hexdigest()
        extraction = self.service.extract(document)
        if extraction.document_confidence is not None and not 0 <= extraction.document_confidence <= 1:
            raise ValueError("service returned invalid document confidence")
        for name, field in extraction.fields.items():
            if field.confidence is not None and not 0 <= field.confidence <= 1:
                raise ValueError(f"service returned invalid confidence for {name}")

        findings = validate(extraction, self.rules)
        failed_rules = tuple(f.rule_id for f in findings if f.status == "FAIL")

        # Human review is required when:
        # 1. Any validation rule FAILs, or
        # 2. Any validation WARNING fires, or
        # 3. The FieldConfidencePolicy (if present) reports unknown or low confidence.
        # The FieldConfidencePolicy is a ValidationRule — it shows up in findings.
        # When no FieldConfidencePolicy is in the rules, the old behaviour
        # (document_confidence is None -> review) is preserved for backward compat.
        has_field_confidence_policy = any(
            isinstance(rule, FieldConfidencePolicy) for rule in self.rules
        )
        if has_field_confidence_policy:
            # New path: rely solely on validation findings.
            # FAIL or WARNING from any rule -> human review.
            reviewed = bool(failed_rules) or any(
                f.status == "WARNING" for f in findings
            )
        else:
            # Legacy path: document_confidence None -> review (backward compat).
            reviewed = (
                extraction.document_confidence is None
                or extraction.document_confidence < self.confidence_threshold
                or bool(failed_rules)
                or any(f.status == "WARNING" for f in findings)
            )

        extraction_hash = _digest(asdict(extraction))
        approved = self.reviewer.review(extraction) if reviewed else True
        review_record = (
            ReviewRecord.create(
                extraction_hash=extraction_hash,
                reviewer=getattr(self.reviewer, "reviewer", "unattributed"),
                decision="APPROVED" if approved else "REJECTED",
                reason_code=(
                    "human-approved-extraction"
                    if approved else "human-rejected-extraction"
                ),
            )
            if reviewed else None
        )
        if not approved:
            status = "REJECTED"
            reason = "human review rejected extraction"
        elif reviewed:
            status = "APPROVED_BY_HUMAN"
            reason = "human review approved extraction"
        else:
            status = "AUTO_APPROVED"
            reason = "confidence and validation policy passed"

        decision = DecisionRecord(
            status=status,
            reason=reason,
            triggered_rules=failed_rules,
            confidence=extraction.document_confidence,
            human_reviewed=reviewed,
            approved=approved,
            review=review_record,
        )

        decision_hash = _digest({
            "status": status,
            "reviewed": reviewed,
            "approved": approved,
            "review_hash": review_record.content_hash() if review_record else None,
        })
        evidence = EvidenceRecord.create(
            document_hash=document_hash,
            operation=self.service.name,
            configuration={"confidence_threshold": self.confidence_threshold},
            extraction_hash=extraction_hash,
            decision_hash=decision_hash,
            decision=status,
            field_count=len(extraction.fields),
            reviewed=reviewed,
            review=review_record.to_dict() if review_record else None,
        )
        unsigned = {
            "document_sha256": document_hash,
            "extraction": asdict(extraction),
            "reviewed": reviewed,
            "approved": approved,
            "status": status,
            "record_sha256": evidence.record_sha256,
        }
        canonical = json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()
        return PipelineResult(
            status=status,
            document_sha256=document_hash,
            extraction=extraction,
            reviewed=reviewed,
            approved=approved,
            evidence_sha256=hashlib.sha256(canonical).hexdigest(),
            evidence=evidence,
            validation=findings,
            decision=decision,
        )
