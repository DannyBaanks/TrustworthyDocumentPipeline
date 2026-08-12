"""Deterministic document pipeline with confidence and evidence gates."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Protocol

from .evidence import EvidenceRecord, _digest


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

    def to_dict(self) -> dict[str, object]:
        value = asdict(self)
        value["extraction"] = asdict(self.extraction)
        return value


class DocumentPipeline:
    def __init__(self, service: DocumentService, reviewer: HumanReviewer,
                 *, confidence_threshold: float = 0.85) -> None:
        if not 0 <= confidence_threshold <= 1:
            raise ValueError("confidence_threshold must be between 0 and 1")
        self.service = service
        self.reviewer = reviewer
        self.confidence_threshold = confidence_threshold

    def run(self, document: Document) -> PipelineResult:
        document_hash = hashlib.sha256(document.content).hexdigest()
        extraction = self.service.extract(document)
        if extraction.document_confidence is not None and not 0 <= extraction.document_confidence <= 1:
            raise ValueError("service returned invalid document confidence")
        for name, field in extraction.fields.items():
            if field.confidence is not None and not 0 <= field.confidence <= 1:
                raise ValueError(f"service returned invalid confidence for {name}")

        reviewed = (
            extraction.document_confidence is None
            or extraction.document_confidence < self.confidence_threshold
        )
        approved = self.reviewer.review(extraction) if reviewed else True
        status = "APPROVED" if approved else "REJECTED"
        if not reviewed:
            status = "AUTO_APPROVED"

        extraction_hash = _digest(asdict(extraction))
        decision_hash = _digest({
            "status": status,
            "reviewed": reviewed,
            "approved": approved,
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
        )
