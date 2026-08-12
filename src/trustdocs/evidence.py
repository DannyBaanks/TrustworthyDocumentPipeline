"""Content-addressed evidence nodes and tamper verification."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


def _digest(value: Any) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()


@dataclass(frozen=True, slots=True)
class EvidenceNode:
    id: str
    operation: str
    input_hash: str
    output_hash: str
    metadata: dict[str, object]
    parent_ids: tuple[str, ...]

    @classmethod
    def create(cls, operation: str, input_hash: str, output_hash: str,
               metadata: dict[str, object], parent_ids: tuple[str, ...] = ()) -> "EvidenceNode":
        body = {
            "operation": operation,
            "input_hash": input_hash,
            "output_hash": output_hash,
            "metadata": metadata,
            "parent_ids": parent_ids,
        }
        return cls(_digest(body)[:32], operation, input_hash, output_hash,
                   metadata, parent_ids)

    def valid_id(self) -> bool:
        expected = EvidenceNode.create(
            self.operation, self.input_hash, self.output_hash,
            self.metadata, self.parent_ids,
        )
        return expected.id == self.id


@dataclass(frozen=True, slots=True)
class EvidenceRecord:
    execution_id: str
    nodes: tuple[EvidenceNode, ...]
    decision: str
    record_sha256: str

    @classmethod
    def create(cls, *, document_hash: str, operation: str, configuration: dict[str, object],
               extraction_hash: str, decision_hash: str, decision: str,
               field_count: int, reviewed: bool) -> "EvidenceRecord":
        execution_id = _digest({
            "document_hash": document_hash,
            "operation": operation,
            "configuration": configuration,
        })
        document = EvidenceNode.create(
            "document", "", document_hash, {"execution_id": execution_id}
        )
        extraction = EvidenceNode.create(
            operation, document.output_hash, extraction_hash,
            {"field_count": field_count, "execution_id": execution_id},
            (document.id,),
        )
        parents = [extraction.id]
        nodes = [document, extraction]
        if reviewed:
            review = EvidenceNode.create(
                "human_review", extraction.output_hash, decision_hash,
                {"execution_id": execution_id}, (extraction.id,),
            )
            nodes.append(review)
            parents = [review.id]
        decision_node = EvidenceNode.create(
            "decision", ":".join(parents), decision_hash,
            {"decision": decision, "execution_id": execution_id}, tuple(parents),
        )
        nodes.append(decision_node)
        body = {
            "execution_id": execution_id,
            "nodes": [asdict(node) for node in nodes],
            "decision": decision,
        }
        return cls(execution_id, tuple(nodes), decision, _digest(body))

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": "trustdocs.evidence/1",
            "execution_id": self.execution_id,
            "nodes": [asdict(node) for node in self.nodes],
            "decision": self.decision,
            "record_sha256": self.record_sha256,
        }

    def verify(self) -> tuple[bool, list[str]]:
        errors: list[str] = []
        ids = {node.id for node in self.nodes}
        for node in self.nodes:
            if not node.valid_id():
                errors.append(f"invalid node id: {node.id}")
            for parent_id in node.parent_ids:
                if parent_id not in ids:
                    errors.append(f"missing parent: {parent_id}")
        body = {
            "execution_id": self.execution_id,
            "nodes": [asdict(node) for node in self.nodes],
            "decision": self.decision,
        }
        if _digest(body) != self.record_sha256:
            errors.append("record hash mismatch")
        return not errors, errors


def write_record(path: Path, record: EvidenceRecord) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(record.to_dict(), indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def read_record(path: Path) -> EvidenceRecord:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema") != "trustdocs.evidence/1":
        raise ValueError("unsupported evidence schema")
    nodes = tuple(EvidenceNode(**node) for node in value["nodes"])
    return EvidenceRecord(value["execution_id"], nodes, value["decision"], value["record_sha256"])
