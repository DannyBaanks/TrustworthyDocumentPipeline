# Trustworthy Document Pipeline

An auditable document-processing application for the DevNetwork Nutrient DWS
Challenge. It uses Nutrient's Data Extraction API for structured document
extraction, validates extracted fields, applies a human review policy, and
records integrity-verifiable evidence.

The pipeline is intentionally small:

```text
document -> DWS operation -> normalized extraction -> confidence gate
         -> human review when needed -> verifiable evidence
```

The public core does not contain private infrastructure names, machine paths,
credentials, or undocumented service endpoints. The DWS connection is an
explicit adapter configured by the caller.

## Current Status

The repository contains the deterministic pipeline contract, confidence gate,
validation rules, evidence chain, local fixtures, and an adapter for the
official extraction contract. The real network path has been exercised with a
non-sensitive PDF; credentials and document contents are not part of the repo.

## Quick Start

```powershell
python -m venv .venv
python -m pip install -e .
python -m trustdocs.cli --demo
python -m trustdocs.cli --demo-warning
# Real path: requires NUTRIENT_EXTRACTION_API_KEY
"n" | python -m trustdocs.cli process document.pdf
python -m trustdocs.cli verify document.pdf.evidence.json
```

For a non-interactive demo, pass the decision explicitly:

```powershell
python -m trustdocs.cli process document.pdf --decision reject
python -m trustdocs.cli process document.pdf --decision approve
```

## Design Requirements

- DWS must perform a meaningful core document operation.
- Low-confidence extraction must stop for human review.
- Every decision must be verifiable from recorded input and output hashes.
- Replay is not claimed until the stored evidence is sufficient to reconstruct
  the decision without calling the remote service again.
- Each run exposes an `execution_id` derived from document hash, operation, and
  normalized configuration.
- Secrets must arrive through environment or deployment configuration.
- No absolute machine path is part of the application contract.

The `--demo-warning` fixture demonstrates a low-confidence field producing a
validation warning and human review. The real document path uses the
`/extraction/extract` endpoint with a typed invoice schema and citations.

Replay is deliberately not advertised: the evidence verifies integrity but
does not reconstruct the remote extraction without calling Nutrient again.

## License

MIT. See `LICENSE`.
