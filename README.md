# Trustworthy Document Pipeline

[![tests](https://github.com/DannyBaanks/trustworthy-document-pipeline/actions/workflows/tests.yml/badge.svg)](https://github.com/DannyBaanks/trustworthy-document-pipeline/actions/workflows/tests.yml)

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
python -m trustdocs.cli --demo-inconsistent
python -m trustdocs.cli verify docs/evidence/rejected.json
python -m trustdocs.cli verify docs/evidence/approved.json
```

See [`docs/DEMO.md`](docs/DEMO.md) for the offline cases, sanitized evidence
verification, and the real Nutrient run.

Every command prints a colored, human-readable summary by default -- status,
document/evidence hashes, and which validation rules fired, never the
extracted field values. Pass `--json` for the same data as machine-readable
output.

Continuous integration runs the complete unit suite without requiring an API
key. The real-service path remains an explicit, optional integration step: a
live test is shipped and skips itself when the key is absent.

### Real Nutrient run

The repository ships sample documents in `sample/` (see
[`sample/README.md`](sample/README.md)): a synthetic invoice for the happy
path and an open-access research paper for the "wrong document type" path.

```powershell
python -m trustdocs.cli process sample/invoice.pdf --decision approve
python -m trustdocs.cli verify sample/invoice.pdf.evidence.json
python -m trustdocs.cli process sample/research-paper.pdf --decision reject
python -m trustdocs.cli verify sample/research-paper.pdf.evidence.json
```

Each real call consumes Nutrient API credits (the free tier includes 5,000 per
month). With a key configured, the live integration suite runs the real
contract end to end:

```powershell
python -m unittest tests.test_live_nutrient -v
```

For a non-interactive decision without reading the output, pass it explicitly:

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
validation warning and human review. The `--demo-inconsistent` fixture
demonstrates a cross-field arithmetic check that no raw text pipeline can
perform: it is a concrete reason to use a typed extraction schema instead of
free-form OCR. The real document path uses the `/extraction/extract` endpoint
with a typed invoice schema and citations.

Replay is deliberately not advertised for the extraction step: the evidence
verifies integrity but does not reconstruct the remote extraction without
calling Nutrient again. What is replayable offline is the *decision*: `verify`
recomputes the hash chain and reports the recorded decision without any vendor
call, so an auditor can re-check the outcome without credentials or network.

## License

MIT. See `LICENSE`.
