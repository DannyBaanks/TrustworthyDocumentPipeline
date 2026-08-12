# Trustworthy Document Pipeline

An auditable document-processing application for the DevNetwork Nutrient DWS
Challenge.

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
evidence chain, a local demo adapter, and an official-contract Nutrient DWS
adapter. The real network path requires `NUTRIENT_EXTRACTION_API_KEY` and is
not claimed as executed until a non-sensitive sample document completes it.

## Quick Start

```powershell
python -m venv .venv
python -m pip install -e .
python -m trustdocs.cli --demo
# Real path: requires NUTRIENT_EXTRACTION_API_KEY
python -m trustdocs.cli document.pdf
```

## Design Requirements

- DWS must perform a meaningful core document operation.
- Low-confidence extraction must stop for human review.
- Every decision must be verifiable from recorded input and output hashes.
- Replay is not claimed until the stored evidence is sufficient to reconstruct
  the decision without calling the remote service again.
- Secrets must arrive through environment or deployment configuration.
- No absolute machine path is part of the application contract.

## License

MIT. See `LICENSE`.
