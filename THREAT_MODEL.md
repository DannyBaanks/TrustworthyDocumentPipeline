# Threat Model

## What this system protects against

- **Post-hoc document alteration**: Changing the document after a decision was
  recorded. The document hash in the evidence record no longer matches.

- **Evidence tampering**: Modifying the extraction, decision, or any field in
  the evidence record. Node IDs and the record hash break.

- **Ledger manipulation**: Editing, deleting, inserting, or reordering entries
  in the decision ledger. The chain breaks at the point of tampering.

- **Undetected truncation**: Cutting entries off the end of the ledger. Detectable
  when the head hash is published externally.

- **Decisions without basis**: Every approval or rejection is linked to a
  specific document hash, extraction, and validation outcome that can be
  re-verified offline.

- **Vendor lock-in**: The evidence layer survives extractor replacement. Two
  different extractors produce different hashes but the same verifiable contract.

## What this system does NOT protect against

- **Malicious operator**: Someone who records a decision they should not have
  made. The evidence proves what was decided; it does not prove the decision
  was correct.

- **Offline extraction replay**: The evidence verifies integrity; it does not
  re-run the remote extraction without calling the vendor again.

- **Availability**: This is a tamper-evident log, not a high-availability system.

- **Compromised endpoint**: If the system is compromised before evidence is
  recorded, the evidence reflects the compromised state.

- **Pre-recording attacks**: Changes made before the pipeline runs are outside
  the scope. The system starts recording from the moment it receives a document.

## Verification model

| Layer | What it checks | Offline? |
|-------|---------------|----------|
| Evidence record | Document hash, extraction hash, decision hash, node integrity | Yes |
| Ledger chain | Entry ordering, content integrity, chain links | Yes |
| Head anchor | Tail truncation via externally published hash | Yes |

## Running the attack demo

```
python -m trustdocs attack
```

This runs every attack vector listed above and shows which ones the system
catches and which it cannot.
