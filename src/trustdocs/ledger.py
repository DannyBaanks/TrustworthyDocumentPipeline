"""Append-only ledger of decisions.

An evidence record proves its own integrity and nothing about its neighbours.
Delete one file from a directory of evidence and every remaining file still
verifies perfectly -- which means a per-document scheme cannot answer the first
question an auditor asks: *show me that nothing is missing*.

The ledger answers it by chaining. Each entry carries the hash of the entry
before it, so deleting, inserting, reordering or editing any entry breaks the
chain at a locatable point.

## What this does not do

Chaining cannot detect **truncation of the tail**. Cut the last N entries off
and what remains is a genuinely intact, genuinely consecutive, shorter chain.
No self-contained log can tell that apart from a log that simply stopped.

Closing that gap requires an anchor held where whoever writes the ledger cannot
reach it. `head()` returns the value to anchor: publish it from CI on every run
and check the local ledger against the last published value, and truncation
stops being silent -- the record leaves the system and comes back in.

`test_LIMITATION_truncating_the_tail_is_not_detectable` asserts this weakness on
purpose, so it cannot quietly disappear from the documentation.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from .evidence import _digest

SCHEMA = "trustdocs.ledger/1"


@dataclass(frozen=True, slots=True)
class LedgerEntry:
    schema: str
    sequence: int
    prev_entry_sha256: str | None
    recorded_at: str
    execution_id: str
    record_sha256: str
    document_sha256: str
    decision: str
    entry_sha256: str

    @staticmethod
    def body(sequence: int, prev: str | None, recorded_at: str, execution_id: str,
             record_sha256: str, document_sha256: str, decision: str) -> dict:
        """The exact fields the entry hash covers. Anything outside is unsigned."""
        return {
            "sequence": sequence,
            "prev_entry_sha256": prev,
            "recorded_at": recorded_at,
            "execution_id": execution_id,
            "record_sha256": record_sha256,
            "document_sha256": document_sha256,
            "decision": decision,
        }

    def recompute(self) -> str:
        return _digest(self.body(
            self.sequence, self.prev_entry_sha256, self.recorded_at,
            self.execution_id, self.record_sha256, self.document_sha256, self.decision))

    def to_dict(self) -> dict:
        return asdict(self)


class Ledger:
    """A JSONL file, one entry per line, appended in order.

    JSONL rather than a single JSON document on purpose: appending must not
    require rewriting what is already there. A format that rewrites the whole
    file on every decision gives an attacker a legitimate reason for the file to
    change, and gives a crash a chance to lose history.
    """

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    # -- reading ------------------------------------------------------------

    def _raw(self) -> list[dict]:
        if not self.path.exists():
            return []
        rows = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
        return rows

    def entries(self, *, decision: str | None = None) -> list[LedgerEntry]:
        out = [LedgerEntry(**row) for row in self._raw()]
        if decision is not None:
            out = [e for e in out if e.decision == decision]
        return out

    def head(self) -> str | None:
        """Hash of the last entry: the value to anchor outside this system."""
        rows = self._raw()
        return rows[-1]["entry_sha256"] if rows else None

    def find_document(self, document_sha256: str) -> LedgerEntry | None:
        """The decision recorded for a document, or None. Never a guess."""
        for entry in reversed(self.entries()):
            if entry.document_sha256 == document_sha256:
                return entry
        return None

    def summary(self) -> dict:
        entries = self.entries()
        by_decision: dict[str, int] = {}
        for e in entries:
            by_decision[e.decision] = by_decision.get(e.decision, 0) + 1
        return {
            "total": len(entries),
            "by_decision": by_decision,
            "head": self.head(),
            "first_recorded_at": entries[0].recorded_at if entries else None,
            "last_recorded_at": entries[-1].recorded_at if entries else None,
        }

    # -- writing ------------------------------------------------------------

    def append(self, *, execution_id: str, record_sha256: str,
               document_sha256: str, decision: str,
               recorded_at: str | None = None) -> LedgerEntry:
        rows = self._raw()
        sequence = len(rows)
        prev = rows[-1]["entry_sha256"] if rows else None
        recorded_at = recorded_at or datetime.now(UTC).isoformat()

        entry_sha256 = _digest(LedgerEntry.body(
            sequence, prev, recorded_at, execution_id,
            record_sha256, document_sha256, decision))

        entry = LedgerEntry(
            schema=SCHEMA, sequence=sequence, prev_entry_sha256=prev,
            recorded_at=recorded_at, execution_id=execution_id,
            record_sha256=record_sha256, document_sha256=document_sha256,
            decision=decision, entry_sha256=entry_sha256)

        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry.to_dict(), sort_keys=True,
                                    separators=(",", ":")) + "\n")
        return entry


def verify_ledger(path: Path | str, *, expected_head: str | None = None
                  ) -> tuple[bool, list[str]]:
    """Walk the chain and report every break, not only the first.

    Stopping at the first error would hide the shape of the damage: one edited
    entry looks the same as a rewritten history until you see how many links
    fail.

    Pass `expected_head` (an anchor published elsewhere) to also catch a
    truncated tail, which the chain alone cannot see.
    """
    path = Path(path)
    errors: list[str] = []

    if not path.exists():
        return False, [f"ledger not found: {path}"]

    rows = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            errors.append(f"line {number}: not valid JSON ({exc.msg})")

    prev_hash: str | None = None
    for index, row in enumerate(rows):
        where = f"entry {row.get('sequence', f'at line {index}')}"

        if row.get("schema") != SCHEMA:
            errors.append(f"{where}: unsupported schema {row.get('schema')!r}")
            continue
        try:
            entry = LedgerEntry(**row)
        except TypeError as exc:
            errors.append(f"{where}: malformed entry ({exc})")
            continue

        if entry.sequence != index:
            errors.append(
                f"{where}: sequence gap -- expected {index}, found {entry.sequence}; "
                "an entry is missing or the file was reordered")

        if entry.prev_entry_sha256 != prev_hash:
            errors.append(
                f"{where}: broken link -- points at {entry.prev_entry_sha256!r} "
                f"but the previous entry hashes to {prev_hash!r}")

        if entry.recompute() != entry.entry_sha256:
            errors.append(f"{where}: content was altered after it was recorded")

        prev_hash = entry.entry_sha256

    if expected_head is not None and prev_hash != expected_head:
        errors.append(
            f"head mismatch -- ledger ends at {prev_hash!r} but the published anchor "
            f"says {expected_head!r}; entries were removed from the end")

    return not errors, errors
